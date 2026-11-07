# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货对外动作         #
# =================================== #

"""
假人搬货的动作层：每个函数对应前端一个 action。

职责固定为三件事：
1. 校验入参（缺参、越界、类型不对都翻译成 AppError）；
2. 组装（调 core 的纯函数做计算，读设置里的口径）；
3. 读写文档（站点表 / 台账 / 订单草稿都落在 ctx.doc_load / doc_save 里）。

本层不直接操作游戏窗口：命令只是字符串，真实发送在 run_start 里交给
platform/autoinput.py 的 CommandRunner。所以除 run_* 外，所有动作都可以
在非 Windows 环境跑通。

文档键：
    stations  站点表 {"version": 1, "stations": [...]}
    orders    台账 {"version": 1, "orders": [...]}，最多 200 条
    draft     订单草稿 {"version": 1, origin, dest, boxes, operation, savedAt}
"""

from __future__ import annotations

import json
import threading
import time
import uuid

from lspkit.errors import AppError
from lspkit.platform import params
from lspkit.platform.autoinput import CommandRunner, InputConfig, diagnose as run_diagnose
from lspkit.platform.autoinput import is_supported as autoinput_supported

from .constants import (
    DIMENSIONS,
    FINAL_MESSAGE,
    MAX_BOXES,
    MAX_COMMANDS,
    MAX_IMPORT_BYTES,
    MAX_ORDERS,
    OPERATIONS,
)
from .core import naming
from .core import stations as station_core
from .core.plan import build_plan, format_coord
from .legacy import parse as parse_legacy

# 三个文档键必须与工具 id 一起使用：ctx.doc_load("puppet", DOC_STATIONS)。
DOC_STATIONS = "stations"
DOC_ORDERS = "orders"
DOC_DRAFT = "draft"

# ------ 台账里每条运单最多保存多少条命令（够用，又不会把 JSON 撑爆） ------ #
MAX_HISTORY_COMMANDS = 200

# ------ 运行中的执行器：runId → {record, runner, gate} ------ #
# 进程内单例：同一时间只允许一个运单在跑，见 run_start 的 RUN_BUSY 判断.
_RUNS: dict = {}
# 前端不带 runId 时默认查最近一次运单（status / stop / continue 都是）.
_LAST_RUN: dict = {"id": ""}
# 保护 _RUNS / _LAST_RUN 的锁；worker 线程与动作线程都会碰这两个结构.
_LOCK = threading.Lock()
# 单个运单最多留多少行日志，超出丢弃最旧的.
_MAX_LOG = 120
# 内存里最多留多少个已结束的运单，超出由 _prune_runs 回收.
_MAX_RUNS = 20


class _BatchGate:
    """
    批间闸门：runner 每发完一批就 poll 一次，run_continue 命中后放行.

    只做「点一下」，不保存跨批状态；中断由 runner 自己轮询 ESC / stop()。

    poll 是「读并清空」语义：一次 open 只放行一批，避免一次点击连放两批。
    """

    def __init__(self) -> None:
        # Event 而非 bool：runner 在别的线程里等，需要线程安全的置位 / 清理.
        self._hit = threading.Event()

    def open(self) -> None:
        """由 run_continue 调用，标记「用户已确认，可以发下一批」."""
        self._hit.set()

    def poll(self) -> bool:
        """取走一次确认；返回 True 表示这一批可以继续发."""

        if self._hit.is_set():
            self._hit.clear()
            return True
        return False


# =================================== #
# @Section: 站点                       #
# =================================== #
def stations_list(payload: dict, ctx) -> dict:
    """
    列出站点表.

    读取时会顺带做一次「软校验」：无法规整的条目直接丢弃，前缀重复的只留第一条
    （见 _load_stations），所以返回的条数可能少于磁盘上的条数。
    """

    return {"stations": _load_stations(ctx)}


def stations_save(payload: dict, ctx) -> dict:
    """
    新增或修改一个站点（按 id 匹配，id 缺省时沿用前缀）.

    站点字段校验在 core/stations.normalize；校验失败统一报 INVALID_STATION。
    created=True 表示新增，False 表示覆盖了已有站点。
    """

    station = params.obj(payload, "station")
    try:
        stations, created = station_core.upsert(_load_stations(ctx), station)
    except ValueError as exc:
        # ValueError 是 core 层的校验失败，翻译成可展示的错误码.
        raise AppError("INVALID_STATION", str(exc)) from None
    _save_stations(ctx, stations)
    return {"stations": stations, "created": created}


def stations_delete(payload: dict, ctx) -> dict:
    """
    按 id 删除站点；id 不存在时报 STATION_NOT_FOUND.

    已生成的运单 / 台账里的站点快照不受影响，它们保存的是当时的副本。
    """

    station_id = _text(payload, "id", "站点 id")
    try:
        stations = station_core.remove(_load_stations(ctx), station_id)
    except ValueError as exc:
        raise AppError("STATION_NOT_FOUND", str(exc)) from None
    _save_stations(ctx, stations)
    return {"stations": stations}


def stations_import(payload: dict, ctx) -> dict:
    """
    导入站点：自动识别 JSON（含旧版 stops.json）与「名称 x y z 前缀」文本.

    流程：先由 legacy.parse 解析成原始 dict 列表 → 逐条 normalize 并丢弃非法项
    → 按前缀去重 → 与现有站点 merge（已存在则覆盖，不存在则追加）→ 整体落盘。

    返回里同时给出 added / updated / duplicated 计数、被跳过的条目原因与 warnings，
    前端据此提示「导入了 N 条，跳过 M 条」。一条都没解析出来时直接报 NO_STATIONS，
    不写盘，避免把现有站点覆盖成空表。
    """

    text = _text(payload, "text", "导入内容", limit=MAX_IMPORT_BYTES)
    # 文本里没写维度时的兜底维度；JSON 里缺维度也用它.
    default_dimension = params.choice(
        payload, "defaultDimension", DIMENSIONS, default="overworld"
    )

    try:
        parsed = parse_legacy(text, default_dimension)
    except ValueError as exc:
        # 结构性错误（空内容 / 坏 JSON / 无法识别的结构）直接整批拒绝.
        raise AppError("INVALID_IMPORT", str(exc)) from None

    skipped = list(parsed["skipped"])
    valid: list = []
    seen: set = set()
    for raw in parsed["stations"]:
        try:
            item = station_core.normalize(raw)
        except ValueError as exc:
            # 单条不合法不打断整批，记下来源与原因继续.
            skipped.append({"source": raw.get("name", "?"), "reason": str(exc)})
            continue
        # 同一批里前缀重复：保留先出现的，后来的进 skipped.
        if item["prefix"] in seen:
            skipped.append({"source": item["name"], "reason": "前缀重复"})
            continue
        seen.add(item["prefix"])
        valid.append(item)

    if not valid:
        raise AppError(
            "NO_STATIONS",
            "没有解析出可用的站点",
            "支持旧版 stops.json 或「名称 x y z 前缀」文本",
        )

    try:
        stations, stats = station_core.merge(_load_stations(ctx), valid)
    except ValueError as exc:
        # merge 的失败通常是超上限或 id / 前缀冲突，整批不落盘.
        raise AppError("INVALID_IMPORT", str(exc)) from None

    _save_stations(ctx, stations)
    return {
        "stations": stations,
        "format": parsed["format"],
        "added": stats["added"],
        "updated": stats["updated"],
        "duplicated": stats["duplicated"],
        "skipped": skipped,
        "warnings": parsed["warnings"],
    }


# =================================== #
# @Section: 导出站点                   #
# =================================== #
def stations_export(payload: dict, ctx) -> dict:
    """
    导出站点：JSON（默认，可再次导入）或「名称 x y z 前缀 维度」文本.

    只返回内容与建议文件名，真正下载由前端完成（本层不写文件）。
    JSON 结构 {"version": 1, "stations": [...]}，与导入的识别规则对应；
    文本每行 7 列：名称 x y z 前缀 分组 维度，分组为空写 "-"（见 legacy 的解析）。
    """

    stations = _load_stations(ctx)
    if not stations:
        raise AppError("NO_STATIONS", "还没有可导出的站点")

    fmt = params.choice(payload, "format", ("json", "text"), default="json")
    if fmt == "text":
        # 名称里允许空格，所以解析端从右往左取列；这里直接空格拼接即可.
        lines = [
            " ".join(
                (
                    station["name"],
                    format_coord(station["x"]),
                    format_coord(station["y"]),
                    format_coord(station["z"]),
                    station["prefix"],
                    station.get("group") or "-",
                    station["dimension"],
                )
            )
            for station in stations
        ]
        text = "\n".join(lines) + "\n"
        filename = "puppet_stations.txt"
    else:
        # ensure_ascii=False 保证中文站点名可读；indent 让 diff 好看.
        text = json.dumps(
            {"version": 1, "stations": stations}, ensure_ascii=False, indent=2
        )
        filename = "puppet_stations.json"

    return {
        "filename": filename,
        "text": text,
        "count": len(stations),
        "format": fmt,
    }


# =================================== #
# @Section: 运单                       #
# =================================== #
def plan_action(payload: dict, ctx) -> dict:
    """
    生成一张运单（不执行）：盒数 → 假人数 → 批次 → spawn / kill 命令.

    口径全部来自设置（boxesPerBot / botsPerBatch / nameTemplate），
    这里额外补两段前端要用的信息：
    - estimate：按「0.9 秒基础耗时 + commandInterval」估算的命令耗时；
    - settings：回显 commandInterval 与 allowExecute，决定前端是否显示执行按钮。
    """

    settings = ctx.settings("puppet")
    stations = _load_stations(ctx)

    origin_id = _text(payload, "origin", "始发站")
    dest_id = _text(payload, "dest", "目的站")
    boxes = params.integer(
        payload, "boxes", minimum=1, maximum=MAX_BOXES, label="运输数量"
    )
    # 未传操作时默认在始发站生成假人.
    operation = params.choice(
        payload, "operation", OPERATIONS, default="spawn_at_origin"
    )

    origin = station_core.find(stations, origin_id)
    dest = station_core.find(stations, dest_id)
    if origin is None:
        raise AppError("STATION_NOT_FOUND", f"没有找到始发站：{origin_id}")
    if dest is None:
        raise AppError("STATION_NOT_FOUND", f"没有找到目的站：{dest_id}")

    try:
        result = build_plan(
            origin,
            dest,
            boxes,
            operation=operation,
            boxes_per_bot=int(settings["boxesPerBot"]),
            bots_per_batch=int(settings["botsPerBatch"]),
            name_template=str(settings["nameTemplate"]),
        )
    except ValueError as exc:
        # 同站点、盒数非整数、名字超长等都从这里出去.
        raise AppError("INVALID_PLAN", str(exc)) from None

    # 0.9 秒是每条命令的固定开销（聚焦、粘贴、回车），加上用户设的间隔.
    per_command = 0.9 + float(settings["commandInterval"])
    result["estimate"] = {
        "perCommand": round(per_command, 1),
        "spawnSeconds": round(len(result["commands"]) * per_command),
        "killSeconds": round(len(result["killCommands"]) * per_command),
    }
    result["settings"] = {
        "commandInterval": settings["commandInterval"],
        "allowExecute": bool(settings["allowExecute"]),
    }
    return result


def history_list(payload: dict, ctx) -> dict:
    """
    读取台账（最近 200 条运单），按写入顺序返回，最新的在末尾.
    """

    return {"orders": _load_orders(ctx)}


def history_clear(payload: dict, ctx) -> dict:
    """
    清空台账（只清 orders，不动站点与草稿）.
    """

    ctx.doc_save("puppet", DOC_ORDERS, {"version": 1, "orders": []})
    return {"orders": []}


# =================================== #
# @Section: 执行                       #
# =================================== #
def run_start(payload: dict, ctx) -> dict:
    """
    开始一次真实执行：把命令交给 CommandRunner，在后台线程里逐条发进游戏.

    三道前置检查按顺序做，任一不过就报错且不创建运单：
    设置里必须开启 allowExecute（安全开关）、必须是 Windows（自动输入依赖 Win32）、
    当前不能已有运单在跑（同一时间只允许一个）。

    payload:
        commands  命令文本列表，每条 ≤256 字符，空串会被丢掉
        phase     "spawn" 或 "kill"，只用于台账标记
        batchSize 每批发多少条，0 表示不分批、一次发完
        meta      台账用的上下文（站点、盒数、假人数、名字、spawnStation）

    batchSize > 0 时创建 _BatchGate：runner 每发完一批就停住，
    等前端调 run_continue 放行，实现「批间人工确认」。
    返回 {runId, total}，后续用 run_status 轮询进度。
    """

    settings = ctx.settings("puppet")
    if not bool(settings["allowExecute"]):
        raise AppError(
            "EXECUTE_DISABLED",
            "执行模式未开启",
            "请到设置 → 执行 中打开「允许自动输入」，再重试",
        )
    if not autoinput_supported():
        raise AppError("NOT_WINDOWS", "自动输入只支持 Windows")

    commands = payload.get("commands")
    if not isinstance(commands, list) or not commands:
        raise AppError("INVALID_PAYLOAD", "缺少要执行的命令列表")
    # 上限防止一次排几千条命令，也保持与计划生成的上限一致.
    if len(commands) > MAX_COMMANDS:
        raise AppError("TOO_MANY_COMMANDS", f"一次最多执行 {MAX_COMMANDS} 条命令")

    # 清洗：去首尾空白、丢空行、超长报错。保留原顺序，不做去重.
    cleaned: list = []
    for raw in commands:
        if not isinstance(raw, str):
            raise AppError("INVALID_PAYLOAD", "命令必须是字符串")
        text = raw.strip()
        if not text:
            continue
        if len(text) > 256:
            raise AppError("COMMAND_TOO_LONG", "单条命令超过 256 字符", text[:60])
        cleaned.append(text)
    if not cleaned:
        raise AppError("INVALID_PAYLOAD", "没有可执行的命令")

    phase = params.choice(payload, "phase", ("spawn", "kill"), default="spawn")
    batch_size = params.integer(
        payload, "batchSize", default=0, minimum=0, maximum=MAX_COMMANDS,
        label="每批命令数",
    )
    # meta 只做透传与兜底：前端没给或给错类型时按空对象处理，不影响执行.
    meta = payload.get("meta")
    meta = meta if isinstance(meta, dict) else {}

    with _LOCK:
        # 检查与占位必须在同一把锁里，否则两个并发请求会同时通过.
        if any(run["record"]["state"] == "running" for run in _RUNS.values()):
            raise AppError("RUN_BUSY", "上一次执行还没结束，请先等待或中断")
        run_id = uuid.uuid4().hex[:8]
        record = {
            "id": run_id,
            "state": "running",
            "phase": phase,
            "total": len(cleaned),
            "sent": 0,
            "index": 0,
            "current": "",
            "logs": [],
            "startedAt": time.time(),
            "finishedAt": None,
            "error": "",
            "meta": meta,
            "batchSize": batch_size,
            "batch": 0,
            # 批数向上取整：7 条、每批 3 条 → 3 批（3/3/1）.
            "batches": (len(cleaned) + batch_size - 1) // batch_size if batch_size else 0,
            # waiting=True 表示停在批间闸门等用户点「继续」.
            "waiting": False,
        }
        # 不分批就不建闸门，runner 拿到 None 会连续发完.
        gate = _BatchGate() if batch_size else None
        _RUNS[run_id] = {"record": record, "runner": None, "gate": gate}
        _LAST_RUN["id"] = run_id

    # 执行参数全部来自设置；final_message 是全部发完后补发的一条聊天消息.
    config = InputConfig(
        start_delay=float(settings["startDelay"]),
        command_interval=float(settings["commandInterval"]),
        input_mode=str(settings["inputMode"]),
        require_focus=bool(settings["requireFocus"]),
        max_attempts=int(settings["maxAttempts"]),
        restore_clipboard=bool(settings["restoreClipboard"]),
        final_message=FINAL_MESSAGE,
    )

    # 回调都在 runner 的工作线程里触发，因此内部一律加 _LOCK.
    runner = CommandRunner(
        config=config,
        logger=lambda text: _log(run_id, text),
        on_progress=lambda index, total, command: _progress(
            run_id, index, total, command
        ),
        batch_size=batch_size,
        batch_gate=gate,
        on_wait=lambda waiting, batch, total: _wait_state(
            run_id, waiting, batch, total
        ),
    )
    _RUNS[run_id]["runner"] = runner
    # daemon 线程：应用退出时不等它，避免关窗卡住；中断由 stop / ESC 负责.
    threading.Thread(
        target=_worker,
        args=(ctx, run_id, runner, cleaned, meta, phase),
        name=f"puppet-{run_id}",
        daemon=True,
    ).start()
    return {"runId": run_id, "total": len(cleaned)}


def run_status(payload: dict, ctx) -> dict:
    """
    查询一次执行的状态快照（轮询用）.

    不带 runId 时取最近一次运单；连最近一次都没有则返回 idle。
    返回 record 的浅拷贝，日志只取最近 40 行，并补一个 elapsed 秒数；
    运单结束后 elapsed 固定为总耗时。
    """

    run_id = payload.get("runId") or _LAST_RUN["id"]
    if not run_id:
        return {"state": "idle", "total": 0, "sent": 0}
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            # 超过 _MAX_RUNS 被回收的旧运单也会落到这里.
            raise AppError("RUN_NOT_FOUND", f"没有找到执行记录：{run_id}")
        record = dict(entry["record"])
        record["logs"] = list(record["logs"])[-40:]
        # 未结束时用当前时间算，保证进度条上的耗时一直在走.
        record["elapsed"] = round(
            (record["finishedAt"] or time.time()) - record["startedAt"], 1
        )
    return record


def run_stop(payload: dict, ctx) -> dict:
    """
    请求中断当前运单：只是置一个停止标志，真正停下由 runner 轮询后自行收尾.

    所以返回 stopping=True 不代表已经停了，前端应继续轮询 run_status 直到
    state 变成 aborted / done。
    """

    run_id = payload.get("runId") or _LAST_RUN["id"]
    with _LOCK:
        entry = _RUNS.get(run_id)
        runner = entry["runner"] if entry else None
    if runner is None:
        raise AppError("RUN_NOT_FOUND", "没有正在执行的运单")
    runner.stop()
    _log(run_id, "已请求中断")
    return {"runId": run_id, "stopping": True}


def run_continue(payload: dict, ctx) -> dict:
    """
    放行下一批：只对停在批间闸门的运单有效.

    不在等待中时返回 continued=False，不视为错误（重复点击 / 已结束时都能安全调用）。

    放行动作本身只是给闸门置位，runner 下一轮 poll 取走后才真正继续发。
    """

    run_id = payload.get("runId") or _LAST_RUN["id"]
    if not run_id:
        raise AppError("RUN_NOT_FOUND", "没有正在执行的运单")
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            raise AppError("RUN_NOT_FOUND", f"没有找到执行记录：{run_id}")
        record = entry["record"]
        # 已经结束（done / aborted / error）时不再放行，直接回报当前状态.
        if record["state"] != "running":
            return {"runId": run_id, "continued": False, "state": record["state"]}
        gate = entry.get("gate")
        # 不分批的运行没有闸门；没在等待说明还没到批末或已经开始下一批.
        if not record.get("waiting") or gate is None:
            return {"runId": run_id, "continued": False, "state": record["state"]}
        gate.open()
        record["waiting"] = False
        batch = int(record.get("batch", 0))
        batches = int(record.get("batches", 0))
    # 日志里报「第几批」用的是刚放行完的批号 + 1，即即将开始的那批.
    _log(run_id, f"已确认，继续第 {batch + 1}/{batches} 批")
    return {"runId": run_id, "continued": True, "state": "running"}


def diagnose_action(payload: dict, ctx) -> dict:
    """
    环境自检：平台是否支持自动输入、各项检查结果（给「执行」面板排错用）.
    """

    return {"supported": autoinput_supported(), "checks": run_diagnose()}


# =================================== #
# @Section: 订单草稿                   #
# =================================== #
def draft_load(payload: dict, ctx) -> dict:
    """
    读取上次留在订单区的始发站 / 目的站 / 数量 / 操作.

    应用每次启动都会先恢复这份草稿，避免重新选站点。

    读出来的内容一律过 _sanitize_draft，所以前端拿到的字段一定齐全：
    站点 id 截到 64 字、盒数夹在 0–MAX_BOXES、操作回落成默认值。
    """

    raw = ctx.doc_load("puppet", DOC_DRAFT, {"version": 1})
    return {"draft": _sanitize_draft(raw)}


def draft_save(payload: dict, ctx) -> dict:
    """
    保存订单草稿，并盖上保存时间（savedAt，秒级，仅用于展示）.

    入参直接就是草稿对象本身，不需要再包一层 "draft" 键。
    """

    draft = _sanitize_draft(payload)
    draft["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    ctx.doc_save("puppet", DOC_DRAFT, {"version": 1, **draft})
    return {"draft": draft}


def _sanitize_draft(raw: dict) -> dict:
    """
    把任意草稿数据夹成安全值，保证前端拿到的字段类型稳定.

    不抛错：坏数据一律回落成空串 / 0 / 默认操作，因为草稿只是便利功能，
    坏了也不该挡住用户下单。
    """

    operation = raw.get("operation")
    if operation not in OPERATIONS:
        operation = "spawn_at_origin"
    try:
        boxes = int(raw.get("boxes") or 0)
    except (TypeError, ValueError):
        # 手改过的草稿里 boxes 可能是 "abc"，直接归零而不是报错.
        boxes = 0
    return {
        "origin": str(raw.get("origin") or "")[:64],
        "dest": str(raw.get("dest") or "")[:64],
        "boxes": max(0, min(boxes, MAX_BOXES)),
        "operation": operation,
        "savedAt": str(raw.get("savedAt") or ""),
    }


# =================================== #
# @Section: 内部                       #
# =================================== #
def _worker(ctx, run_id: str, runner, commands, meta, phase) -> None:
    """
    后台线程主体：跑完整个运单，写台账，再把终态写回内存记录.

    state 判定优先级：有 error → error；被中断 → aborted；否则 done。
    顺序很关键——先落台账再置状态，前端看到「已完成」时台账一定已经写盘。
    """

    report = runner.run(commands)
    state = "aborted" if report.aborted else "done"
    if report.error:
        state = "error"
    # 先写台账再置状态：前端看到「已完成」时，台账一定已经落盘
    _append_history(ctx, meta, phase, state, report, commands)
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is not None:
            record = entry["record"]
            record.update(
                state=state,
                sent=report.sent,
                index=report.last_index,
                finishedAt=time.time(),
                error=report.error,
            )
            record["logs"].append(report.summary())
            record["logs"] = record["logs"][-_MAX_LOG:]
        _prune_runs()


def _prune_runs() -> None:
    """只保留最近若干条已结束的执行记录."""

    finished = [
        run_id
        for run_id, entry in _RUNS.items()
        if entry["record"]["state"] != "running"
    ]
    # 按插入顺序保留最后 _MAX_RUNS 条；running 的不参与回收.
    for run_id in finished[: max(0, len(finished) - _MAX_RUNS)]:
        _RUNS.pop(run_id, None)


def _append_history(ctx, meta, phase: str, state: str, report, commands) -> None:
    """
    往台账追加一条运单记录，超过 MAX_ORDERS 条时挤掉最旧的.

    记录里有两份冗余数据：
    - commands：最多 MAX_HISTORY_COMMANDS 条命令原文（单条截到 256 字），
      超出部分丢弃并把 truncated 置 True；
    - meta：origin / dest / boxes / bots / names / spawnStation 的快照，
      站点之后被改名或删除也不影响历史回溯。

    spawnStation 只在 meta 里给了 id 或 name 时才落库，否则为 None。
    整个函数吞掉异常：台账写失败不影响执行结果本身。
    """

    try:
        orders = _load_orders(ctx)
        # 运单号 = 现有最大号 + 1；台账被清空后从 1 重新开始.
        number = 1 + max([int(item.get("no", 0)) for item in orders] or [0])
        stored = [str(item)[:256] for item in commands][:MAX_HISTORY_COMMANDS]
        names = meta.get("names")
        names = [str(item) for item in names][:MAX_HISTORY_COMMANDS] if isinstance(names, list) else []
        spawn = meta.get("spawnStation")
        spawn_station = None
        if isinstance(spawn, dict) and (spawn.get("id") or spawn.get("name")):
            # 只留 4 个字段：坐标等细节在运单快照里已有，台账不必重复存.
            spawn_station = {
                "id": str(spawn.get("id", "")),
                "name": str(spawn.get("name", "")),
                "group": str(spawn.get("group", "")),
                "dimension": str(spawn.get("dimension", "")),
            }
        orders.append(
            {
                "no": number,
                "at": time.strftime("%H:%M"),
                "date": time.strftime("%Y-%m-%d"),
                "origin": str(meta.get("origin", "")),
                "dest": str(meta.get("dest", "")),
                "boxes": int(meta.get("boxes", 0)),
                "bots": int(meta.get("bots", 0)),
                "phase": phase,
                "state": state,
                "sent": report.sent,
                "total": report.total,
                "commands": stored,
                "truncated": len(commands) > len(stored),
                "spawnStation": spawn_station,
                "meta": {
                    "origin": str(meta.get("origin", "")),
                    "dest": str(meta.get("dest", "")),
                    "boxes": int(meta.get("boxes", 0)),
                    "bots": int(meta.get("bots", 0)),
                    "names": names,
                    "spawnStation": spawn_station,
                },
            }
        )
        # 只留最近 MAX_ORDERS 条，写入前就切，避免文件无限增长.
        ctx.doc_save(
            "puppet", DOC_ORDERS, {"version": 1, "orders": orders[-MAX_ORDERS:]}
        )
    except Exception:  # noqa: BLE001 - 台账失败不影响执行结果
        pass


def _log(run_id: str, text: str) -> None:
    """
    往运单日志里追加一行（单行截到 300 字），超出上限就丢最旧的.

    由 runner 的回调在后台线程调用，必须加锁；超长文本截断而不是报错。
    """

    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            return
        logs = entry["record"]["logs"]
        logs.append(str(text)[:300])
        if len(logs) > _MAX_LOG:
            del logs[: len(logs) - _MAX_LOG]


def _wait_state(run_id: str, waiting: bool, batch: int, total: int) -> None:
    """
    记录「是否停在批间闸门」以及当前批号 / 总批数（runner 的 on_wait 回调）.
    """

    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            return
        entry["record"].update(waiting=bool(waiting), batch=int(batch), batches=int(total))


def _progress(run_id: str, index: int, total: int, command: str) -> None:
    """
    更新进度（runner 的 on_progress 回调）：当前第几条、共几条、正在发什么.

    current 截到 200 字，只用于界面显示，不参与逻辑。
    """

    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            return
        # sent 跟着进度实时更新，界面上的进度条 / 计数不用等整单结束
        entry["record"].update(
            index=index, sent=index, total=total, current=command[:200]
        )


def _load_stations(ctx) -> list:
    """
    读取站点表并做软校验：非法条目静默丢弃，前缀重复只留第一条.

    这里不抛错，因为站点表是外部文件，损坏时应当仍能打开工具；
    需要严格校验的场合（保存 / 导入）走 core 层的 upsert / merge。
    """

    doc = ctx.doc_load("puppet", DOC_STATIONS, {"version": 1, "stations": []})
    raw = doc.get("stations")
    if not isinstance(raw, list):
        return []
    stations: list = []
    seen: set = set()
    for item in raw:
        try:
            station = station_core.normalize(item)
        except ValueError:
            continue
        if station["prefix"] in seen:
            continue
        seen.add(station["prefix"])
        stations.append(station)
    return stations


def _save_stations(ctx, stations: list) -> None:
    """
    整表覆盖写入站点文档（调用方负责先做校验与去重）.
    """

    ctx.doc_save("puppet", DOC_STATIONS, {"version": 1, "stations": stations})


def _load_orders(ctx) -> list:
    """
    读取台账；文件缺失或结构不对时返回空列表，不抛错.
    """

    doc = ctx.doc_load("puppet", DOC_ORDERS, {"version": 1, "orders": []})
    raw = doc.get("orders")
    return raw if isinstance(raw, list) else []


def _text(payload: dict, key: str, label: str, limit: int = 2000) -> str:
    """
    取一个必填字符串参数：去首尾空白、校验非空与长度.

    label 是给用户看的字段名（如「始发站」），会出现在报错里；
    limit 默认 2000 字，导入场景会传 MAX_IMPORT_BYTES。
    """

    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppError("INVALID_PAYLOAD", f"缺少参数：{label}")
    text = value.strip()
    if len(text) > limit:
        raise AppError("INVALID_INPUT", f"「{label}」过长")
    return text


# ------ 命名模板校验导出给前端预览用 ------ #
def validate_template_action(payload: dict, ctx) -> dict:
    """
    校验命名模板并回显（未传时用设置里的当前值）.

    前端在设置页边输边调，只想知道「能不能用」，所以返回规整后的模板文本；
    不合法时抛 INVALID_TEMPLATE，消息直接来自 core/naming 的中文说明。
    """

    template = payload.get("template") or ctx.settings("puppet")["nameTemplate"]
    try:
        text = naming.validate_template(str(template))
    except ValueError as exc:
        raise AppError("INVALID_TEMPLATE", str(exc)) from None
    return {"template": text}
