# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货对外动作         #
# =================================== #

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

DOC_STATIONS = "stations"
DOC_ORDERS = "orders"
DOC_DRAFT = "draft"

# ------ 台账里每条运单最多保存多少条命令（够用，又不会把 JSON 撑爆） ------ #
MAX_HISTORY_COMMANDS = 200

# ------ 运行中的执行器：runId → {record, runner, gate} ------ #
_RUNS: dict = {}
_LAST_RUN: dict = {"id": ""}
_LOCK = threading.Lock()
_MAX_LOG = 120
_MAX_RUNS = 20


class _BatchGate:
    """
    批间闸门：runner 每发完一批就 poll 一次，run_continue 命中后放行.

    只做「点一下」，不保存跨批状态；中断由 runner 自己轮询 ESC / stop()。
    """

    def __init__(self) -> None:
        self._hit = threading.Event()

    def open(self) -> None:
        self._hit.set()

    def poll(self) -> bool:
        if self._hit.is_set():
            self._hit.clear()
            return True
        return False


# =================================== #
# @Section: 站点                       #
# =================================== #
def stations_list(payload: dict, ctx) -> dict:
    return {"stations": _load_stations(ctx)}


def stations_save(payload: dict, ctx) -> dict:
    station = params.obj(payload, "station")
    try:
        stations, created = station_core.upsert(_load_stations(ctx), station)
    except ValueError as exc:
        raise AppError("INVALID_STATION", str(exc)) from None
    _save_stations(ctx, stations)
    return {"stations": stations, "created": created}


def stations_delete(payload: dict, ctx) -> dict:
    station_id = _text(payload, "id", "站点 id")
    try:
        stations = station_core.remove(_load_stations(ctx), station_id)
    except ValueError as exc:
        raise AppError("STATION_NOT_FOUND", str(exc)) from None
    _save_stations(ctx, stations)
    return {"stations": stations}


def stations_import(payload: dict, ctx) -> dict:
    text = _text(payload, "text", "导入内容", limit=MAX_IMPORT_BYTES)
    default_dimension = params.choice(
        payload, "defaultDimension", DIMENSIONS, default="overworld"
    )

    try:
        parsed = parse_legacy(text, default_dimension)
    except ValueError as exc:
        raise AppError("INVALID_IMPORT", str(exc)) from None

    skipped = list(parsed["skipped"])
    valid: list = []
    seen: set = set()
    for raw in parsed["stations"]:
        try:
            item = station_core.normalize(raw)
        except ValueError as exc:
            skipped.append({"source": raw.get("name", "?"), "reason": str(exc)})
            continue
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
    """

    stations = _load_stations(ctx)
    if not stations:
        raise AppError("NO_STATIONS", "还没有可导出的站点")

    fmt = params.choice(payload, "format", ("json", "text"), default="json")
    if fmt == "text":
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
    settings = ctx.settings("puppet")
    stations = _load_stations(ctx)

    origin_id = _text(payload, "origin", "始发站")
    dest_id = _text(payload, "dest", "目的站")
    boxes = params.integer(
        payload, "boxes", minimum=1, maximum=MAX_BOXES, label="运输数量"
    )
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
        raise AppError("INVALID_PLAN", str(exc)) from None

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
    return {"orders": _load_orders(ctx)}


def history_clear(payload: dict, ctx) -> dict:
    ctx.doc_save("puppet", DOC_ORDERS, {"version": 1, "orders": []})
    return {"orders": []}


# =================================== #
# @Section: 执行                       #
# =================================== #
def run_start(payload: dict, ctx) -> dict:
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
    if len(commands) > MAX_COMMANDS:
        raise AppError("TOO_MANY_COMMANDS", f"一次最多执行 {MAX_COMMANDS} 条命令")

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
    meta = payload.get("meta")
    meta = meta if isinstance(meta, dict) else {}

    with _LOCK:
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
            "batches": (len(cleaned) + batch_size - 1) // batch_size if batch_size else 0,
            "waiting": False,
        }
        gate = _BatchGate() if batch_size else None
        _RUNS[run_id] = {"record": record, "runner": None, "gate": gate}
        _LAST_RUN["id"] = run_id

    config = InputConfig(
        start_delay=float(settings["startDelay"]),
        command_interval=float(settings["commandInterval"]),
        input_mode=str(settings["inputMode"]),
        require_focus=bool(settings["requireFocus"]),
        max_attempts=int(settings["maxAttempts"]),
        restore_clipboard=bool(settings["restoreClipboard"]),
        final_message=FINAL_MESSAGE,
    )

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
    threading.Thread(
        target=_worker,
        args=(ctx, run_id, runner, cleaned, meta, phase),
        name=f"puppet-{run_id}",
        daemon=True,
    ).start()
    return {"runId": run_id, "total": len(cleaned)}


def run_status(payload: dict, ctx) -> dict:
    run_id = payload.get("runId") or _LAST_RUN["id"]
    if not run_id:
        return {"state": "idle", "total": 0, "sent": 0}
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            raise AppError("RUN_NOT_FOUND", f"没有找到执行记录：{run_id}")
        record = dict(entry["record"])
        record["logs"] = list(record["logs"])[-40:]
        record["elapsed"] = round(
            (record["finishedAt"] or time.time()) - record["startedAt"], 1
        )
    return record


def run_stop(payload: dict, ctx) -> dict:
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
    """

    run_id = payload.get("runId") or _LAST_RUN["id"]
    if not run_id:
        raise AppError("RUN_NOT_FOUND", "没有正在执行的运单")
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            raise AppError("RUN_NOT_FOUND", f"没有找到执行记录：{run_id}")
        record = entry["record"]
        if record["state"] != "running":
            return {"runId": run_id, "continued": False, "state": record["state"]}
        gate = entry.get("gate")
        if not record.get("waiting") or gate is None:
            return {"runId": run_id, "continued": False, "state": record["state"]}
        gate.open()
        record["waiting"] = False
        batch = int(record.get("batch", 0))
        batches = int(record.get("batches", 0))
    _log(run_id, f"已确认，继续第 {batch + 1}/{batches} 批")
    return {"runId": run_id, "continued": True, "state": "running"}


def diagnose_action(payload: dict, ctx) -> dict:
    return {"supported": autoinput_supported(), "checks": run_diagnose()}


# =================================== #
# @Section: 订单草稿                   #
# =================================== #
def draft_load(payload: dict, ctx) -> dict:
    """
    读取上次留在订单区的始发站 / 目的站 / 数量 / 操作.

    应用每次启动都会先恢复这份草稿，避免重新选站点。
    """

    raw = ctx.doc_load("puppet", DOC_DRAFT, {"version": 1})
    return {"draft": _sanitize_draft(raw)}


def draft_save(payload: dict, ctx) -> dict:
    draft = _sanitize_draft(payload)
    draft["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    ctx.doc_save("puppet", DOC_DRAFT, {"version": 1, **draft})
    return {"draft": draft}


def _sanitize_draft(raw: dict) -> dict:
    operation = raw.get("operation")
    if operation not in OPERATIONS:
        operation = "spawn_at_origin"
    try:
        boxes = int(raw.get("boxes") or 0)
    except (TypeError, ValueError):
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
    for run_id in finished[: max(0, len(finished) - _MAX_RUNS)]:
        _RUNS.pop(run_id, None)


def _append_history(ctx, meta, phase: str, state: str, report, commands) -> None:
    try:
        orders = _load_orders(ctx)
        number = 1 + max([int(item.get("no", 0)) for item in orders] or [0])
        stored = [str(item)[:256] for item in commands][:MAX_HISTORY_COMMANDS]
        names = meta.get("names")
        names = [str(item) for item in names][:MAX_HISTORY_COMMANDS] if isinstance(names, list) else []
        spawn = meta.get("spawnStation")
        spawn_station = None
        if isinstance(spawn, dict) and (spawn.get("id") or spawn.get("name")):
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
        ctx.doc_save(
            "puppet", DOC_ORDERS, {"version": 1, "orders": orders[-MAX_ORDERS:]}
        )
    except Exception:  # noqa: BLE001 - 台账失败不影响执行结果
        pass


def _log(run_id: str, text: str) -> None:
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            return
        logs = entry["record"]["logs"]
        logs.append(str(text)[:300])
        if len(logs) > _MAX_LOG:
            del logs[: len(logs) - _MAX_LOG]


def _wait_state(run_id: str, waiting: bool, batch: int, total: int) -> None:
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            return
        entry["record"].update(waiting=bool(waiting), batch=int(batch), batches=int(total))


def _progress(run_id: str, index: int, total: int, command: str) -> None:
    with _LOCK:
        entry = _RUNS.get(run_id)
        if entry is None:
            return
        # sent 跟着进度实时更新，界面上的进度条 / 计数不用等整单结束
        entry["record"].update(
            index=index, sent=index, total=total, current=command[:200]
        )


def _load_stations(ctx) -> list:
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
    ctx.doc_save("puppet", DOC_STATIONS, {"version": 1, "stations": stations})


def _load_orders(ctx) -> list:
    doc = ctx.doc_load("puppet", DOC_ORDERS, {"version": 1, "orders": []})
    raw = doc.get("orders")
    return raw if isinstance(raw, list) else []


def _text(payload: dict, key: str, label: str, limit: int = 2000) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppError("INVALID_PAYLOAD", f"缺少参数：{label}")
    text = value.strip()
    if len(text) > limit:
        raise AppError("INVALID_INPUT", f"「{label}」过长")
    return text


# ------ 命名模板校验导出给前端预览用 ------ #
def validate_template_action(payload: dict, ctx) -> dict:
    template = payload.get("template") or ctx.settings("puppet")["nameTemplate"]
    try:
        text = naming.validate_template(str(template))
    except ValueError as exc:
        raise AppError("INVALID_TEMPLATE", str(exc)) from None
    return {"template": text}
