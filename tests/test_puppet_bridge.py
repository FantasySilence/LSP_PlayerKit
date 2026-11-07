# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货 API 契约        #
# =================================== #
# 测试层：puppet 工具的 Api 契约（站点 / 运单 / 台账 / 草稿 / 执行开关）。
# 策略：临时数据目录 + 真实 Registry；执行链路用假 CommandRunner，
# 批间确认用 dry-run 的真实 CommandRunner + 假 Transport，不碰键鼠。

import time

# 两个站点覆盖「工业区·地点」旧命名（normalize 会拆成 group + name）、
# 两种维度（overworld / the_end）与负坐标。
STATION = {
    "id": "all",
    "name": "重溟洋工业区·全物品",
    "prefix": "all",
    "dimension": "overworld",
    "x": 567,
    "y": 102,
    "z": -595,
}
DEST = {
    "id": "vil",
    "name": "永夜岛工业区·村民交易所",
    "prefix": "vil",
    "dimension": "the_end",
    "x": 655,
    "y": 48,
    "z": -180,
}


def save_station(api, station):
    """保存站点并断言信封成功；返回 data 供后续断言.

    失败时把完整 result 放进 assert 消息，便于定位是哪个字段没通过校验。
    """
    result = api.tool_call("puppet", "stations_save", {"station": station})
    assert result["ok"] is True, result
    return result["data"]


def test_puppet_is_registered(api):
    """验证 puppet 已注册且排在 material 之后.

    输入：默认注册表的 app_state()。
    期望：工具 id 含 puppet，且 material 的下标小于 puppet（侧边栏顺序）。
    """
    ids = [tool["id"] for tool in api.app_state()["data"]["tools"]]
    assert "puppet" in ids
    assert ids.index("material") < ids.index("puppet")


def test_stations_roundtrip(api):
    """验证站点新增、更新与删除的完整往返.

    输入：空站点表 -> 保存 all -> 同 id 改 x=800 -> 删除 all。
    期望：初始为空；首次 created=True；再次 created=False 且 x=800；删除后为空。
    """
    assert api.tool_call("puppet", "stations_list", {})["data"]["stations"] == []
    data = save_station(api, STATION)
    assert len(data["stations"]) == 1
    assert data["created"] is True

    data = save_station(api, dict(STATION, x=800))
    assert data["stations"][0]["x"] == 800
    assert data["created"] is False

    removed = api.tool_call("puppet", "stations_delete", {"id": "all"})
    assert removed["ok"] is True
    assert removed["data"]["stations"] == []


def test_invalid_station_returns_envelope(api):
    """验证非法维度以 INVALID_STATION 信封返回.

    输入：把 STATION 的 dimension 改成 "moon"。
    期望：ok=False，错误码 INVALID_STATION（core.normalize 的 ValueError 被翻译）。
    """
    result = api.tool_call("puppet", "stations_save", {"station": {**STATION, "dimension": "moon"}})
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_STATION"


def test_plan_via_api(api):
    """验证经 API 生成运单的核心口径.

    输入：保存两站，origin=all、dest=vil、boxes=250。
    期望：bots=7（ceil(250/36)）、waves=1；首条命令带 overworld 维度；
          spawnStation 的 group/name 已从「工业区·全物品」拆开。
    """
    save_station(api, STATION)
    save_station(api, DEST)

    result = api.tool_call(
        "puppet", "plan", {"origin": "all", "dest": "vil", "boxes": 250}
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["bots"] == 7
    # 250 盒 / 36 盒每人 = 6.94 -> 7 人；7 人 <= 24 人/批，所以只有 1 批。
    assert data["waves"] == 1
    assert data["commands"][0]["text"].startswith("/execute in minecraft:overworld")
    assert data["estimate"]["spawnSeconds"] > 0
    assert data["spawnStation"]["group"] == "重溟洋工业区"
    assert data["spawnStation"]["name"] == "全物品"


def test_plan_rejects_same_station(api):
    """验证始发站与目的站相同时拒绝生成.

    输入：origin=dest=all、boxes=1。
    期望：ok=False，INVALID_PLAN。
    """
    save_station(api, STATION)
    result = api.tool_call(
        "puppet", "plan", {"origin": "all", "dest": "all", "boxes": 1}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PLAN"


def test_plan_unknown_station(api):
    """验证站点不存在时返回 STATION_NOT_FOUND.

    输入：origin=dest="nope"。
    期望：ok=False，STATION_NOT_FOUND。
    """
    result = api.tool_call(
        "puppet", "plan", {"origin": "nope", "dest": "nope", "boxes": 1}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "STATION_NOT_FOUND"


def test_execute_disabled_by_default(api):
    """验证执行安全开关默认关闭.

    输入：默认设置（allowExecute=False）下调用 run_start。
    期望：ok=False，EXECUTE_DISABLED；不会创建运单或启动线程。
    """
    result = api.tool_call(
        "puppet",
        "run_start",
        {"commands": ["/say hi"], "phase": "spawn", "meta": {}},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "EXECUTE_DISABLED"


def test_stations_import(api):
    """验证从「名称 x y z 前缀」文本导入站点.

    输入：end_concrete 前缀 + defaultDimension=the_end。
    期望：added=1；前缀去掉 end_ 后为 concrete，维度为 the_end。
    """
    text = "永夜岛工业区·混凝土工厂 136 48 8 end_concrete\n"
    # 旧 command.txt 用 end_ / nether_ / ov_ 前缀携带维度，parse 会剥离并归一。
    result = api.tool_call(
        "puppet", "stations_import", {"text": text, "defaultDimension": "the_end"}
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["added"] == 1
    assert data["stations"][0]["prefix"] == "concrete"
    assert data["stations"][0]["dimension"] == "the_end"


def test_stations_export_json_roundtrip(api):
    """验证 JSON 导出后能原样导入.

    输入：两个站点 -> export(format=json) -> 清空 -> 用导出文本导入。
    期望：文件名 .json、count=2；导入 added=2，前缀到维度的映射保持不变。
    """
    save_station(api, STATION)
    save_station(api, DEST)

    exported = api.tool_call("puppet", "stations_export", {"format": "json"})
    assert exported["ok"] is True
    payload = exported["data"]
    assert payload["filename"].endswith(".json")
    assert payload["count"] == 2

    for station in api.tool_call("puppet", "stations_list", {})["data"]["stations"]:
        api.tool_call("puppet", "stations_delete", {"id": station["id"]})

    imported = api.tool_call("puppet", "stations_import", {"text": payload["text"]})
    assert imported["ok"] is True, imported
    assert imported["data"]["added"] == 2
    dimensions = {item["prefix"]: item["dimension"] for item in imported["data"]["stations"]}
    assert dimensions == {"all": "overworld", "vil": "the_end"}


def test_stations_export_text_roundtrip(api):
    """验证文本导出后能原样导入.

    输入：两个站点 -> export(format=text) -> 清空 -> 用导出文本导入。
    期望：文件名 .txt，文本含 the_end；导入后两站维度保持不变。
    """
    save_station(api, STATION)
    save_station(api, DEST)

    payload = api.tool_call("puppet", "stations_export", {"format": "text"})["data"]
    # 导出文本每行 7 列（名称 x y z 前缀 分组 维度），导入端按列数识别。
    assert payload["filename"].endswith(".txt")
    assert "the_end" in payload["text"]

    for station in api.tool_call("puppet", "stations_list", {})["data"]["stations"]:
        api.tool_call("puppet", "stations_delete", {"id": station["id"]})

    imported = api.tool_call(
        "puppet", "stations_import", {"text": payload["text"], "defaultDimension": "overworld"}
    )
    assert imported["ok"] is True, imported
    dimensions = {item["prefix"]: item["dimension"] for item in imported["data"]["stations"]}
    assert dimensions == {"all": "overworld", "vil": "the_end"}


def test_stations_export_text_keeps_group(api):
    """验证文本导出保留分组与短名称.

    输入：一个显式 group=主城、name=仓库 的站点。
    期望：导出文本含「主城」；删除后导入，group 与 name 都恢复。
    """
    grouped = {
        **STATION,
        "name": "仓库",
        "group": "主城",
        "prefix": "wh",
        "id": "wh",
    }
    save_station(api, grouped)
    payload = api.tool_call("puppet", "stations_export", {"format": "text"})["data"]
    assert "主城" in payload["text"]

    api.tool_call("puppet", "stations_delete", {"id": "wh"})
    imported = api.tool_call("puppet", "stations_import", {"text": payload["text"]})
    assert imported["ok"] is True, imported
    station = imported["data"]["stations"][0]
    assert station["group"] == "主城"
    assert station["name"] == "仓库"


def test_stations_export_empty(api):
    """验证空站点表导出时报 NO_STATIONS.

    输入：未保存任何站点。
    期望：ok=False，NO_STATIONS。
    """
    result = api.tool_call("puppet", "stations_export", {})
    assert result["ok"] is False
    assert result["error"]["code"] == "NO_STATIONS"


def test_history_clear(api):
    """验证台账清空.

    输入：空台账先清一次，再清一次并读取。
    期望：两次返回的 orders 都为空；history_list 也是空。
    """
    assert api.tool_call("puppet", "history_clear", {})["data"]["orders"] == []
    assert api.tool_call("puppet", "history_list", {})["data"]["orders"] == []


def test_diagnose_shape(api):
    """验证 diagnose 返回前端约定的结构.

    输入：无参数调用 puppet.diagnose。
    期望：data 含 supported 布尔值，checks 是列表（具体检查项随平台变化）。
    """
    data = api.tool_call("puppet", "diagnose", {})["data"]
    assert "supported" in data and isinstance(data["checks"], list)


class _FakeRunner:
    """只验证线程 / 状态 / 台账链路，不碰真实键盘."""

    last_config = None
    last_kwargs: dict = {}
    # 不实现真实输入，只记录构造参数并回调进度，用来验证 actions 的状态/台账链路。

    def __init__(self, config=None, logger=None, on_progress=None, **kwargs):
        _FakeRunner.last_config = config
        _FakeRunner.last_kwargs = kwargs
        self.logger = logger
        self.on_progress = on_progress

    def run(self, commands):
        """按顺序回调进度并返回 RunReport；不发送任何按键."""
        from lspkit.platform.autoinput import RunReport

        for index, command in enumerate(commands, 1):
            if self.on_progress:
                self.on_progress(index, len(commands), command)
        if self.logger:
            self.logger("fake run done")
        return RunReport(total=len(commands), sent=len(commands), last_index=len(commands))

    def stop(self):
        pass


def test_run_start_to_ledger(api, monkeypatch):
    """验证 run_start 的后台线程、状态轮询与台账落盘.

    输入：allowExecute=True，两条命令，meta 带 origin/dest/boxes/bots/names/spawnStation。
    期望：状态变为 done、sent=2；台账最后一条保留命令、meta 与站点快照；
          runner 的 final_message 是固定的 "Operation completed successfully"。
    """
    import time

    import lspkit.tools.puppet.actions as puppet_actions
    # 把 actions 里的 CommandRunner 换成假实现：这里只验证线程与台账，不碰真实键盘。

    monkeypatch.setattr(puppet_actions, "CommandRunner", _FakeRunner)
    settings = api.settings_get("puppet")["data"]
    settings["allowExecute"] = True
    assert api.settings_save("puppet", settings)["ok"] is True

    start = api.tool_call(
        "puppet",
        "run_start",
        {
            "commands": ["/say a", "/say b"],
            "phase": "spawn",
            "meta": {
                "origin": "all",
                "dest": "vil",
                "boxes": 2,
                "bots": 2,
                "names": ["n1", "n2"],
                "spawnStation": {
                    "id": "all",
                    "name": "重溟洋工业区·全物品",
                    "group": "重溟洋工业区",
                    "dimension": "overworld",
                },
            },
        },
    )
    assert start["ok"] is True, start
    run_id = start["data"]["runId"]

    status = {}
    # 最多轮询 200 × 20ms = 4s，足够后台线程跑完两条假命令。
    for _ in range(200):
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status["state"] != "running":
            break
        time.sleep(0.02)

    assert status["state"] == "done", status
    assert status["sent"] == 2
    orders = api.tool_call("puppet", "history_list", {})["data"]["orders"]
    assert orders[-1]["origin"] == "all"
    assert orders[-1]["sent"] == 2
    assert orders[-1]["state"] == "done"
    assert orders[-1]["commands"] == ["/say a", "/say b"]
    assert orders[-1]["truncated"] is False
    assert orders[-1]["meta"]["names"] == ["n1", "n2"]
    assert orders[-1]["spawnStation"]["id"] == "all"
    assert orders[-1]["spawnStation"]["name"] == "重溟洋工业区·全物品"
    assert orders[-1]["spawnStation"]["group"] == "重溟洋工业区"
    assert orders[-1]["meta"]["spawnStation"]["dimension"] == "overworld"
    assert _FakeRunner.last_config is not None
    # 这条结束提示来自 puppet/constants.FINAL_MESSAGE，不由前端传入。
    assert _FakeRunner.last_config.final_message == "Operation completed successfully"
    # 未指定 batchSize 时 batch_size=0、batch_gate=None，runner 应连续发完。
    assert _FakeRunner.last_kwargs["batch_size"] == 0
    assert _FakeRunner.last_kwargs["batch_gate"] is None


class _QuietTransport:
    """dry-run 用的假 Transport：只提供虚拟时钟与空按键状态."""

    def __init__(self):
        self.time = 0.0
        # 虚拟时钟让 dry-run 的 sleep 不真正等待；所有窗口/按键查询都返回「无事发生」。
        self.keys: set = set()

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += max(seconds, 0.0)

    def key_down(self, key):
        return key in self.keys

    def find_window(self, patterns, klass):
        return None

    def is_window(self, hwnd):
        return False

    def foreground(self):
        return 0

    def activate(self, hwnd):
        return False

    def responsive(self, hwnd, timeout_ms):
        return True

    def tap(self, key, hold):
        return True

    def chord(self, modifiers, key, hold):
        return True

    def type_text(self, text, hold, gap):
        return []

    def clipboard_get(self):
        return None

    def clipboard_set(self, text):
        return True


def _dry_runner(**kwargs):
    """用真实 CommandRunner（dry-run + 假 Transport）走完整的批间闸门."""

    from lspkit.platform.autoinput import CommandRunner, InputConfig

    # dry_run=True 让 CommandRunner 只走控制流（批间闸门、进度、日志），不产生按键。
    kwargs["config"] = InputConfig(
        dry_run=True,
        start_delay=0,
        command_interval=0.01,
        align_ticks=False,
        restore_clipboard=False,
    )
    kwargs["transport"] = _QuietTransport()
    return CommandRunner(**kwargs)


def test_batch_confirmation_roundtrip(api, monkeypatch):
    """验证批间闸门：第一批后停住，run_continue 放行，结束后再点无效.

    输入：4 条命令、batchSize=2，allowExecute=True，dry-run 的真实 runner。
    期望：第一次等待时 waiting=True、batch=1/2、sent=2；继续后 done、sent=4；
          已结束后再 continue 返回 continued=False。
    """
    import lspkit.tools.puppet.actions as puppet_actions

    monkeypatch.setattr(puppet_actions, "CommandRunner", _dry_runner)
    settings = api.settings_get("puppet")["data"]
    settings["allowExecute"] = True
    assert api.settings_save("puppet", settings)["ok"] is True

    start = api.tool_call(
        "puppet",
        "run_start",
        {
            "commands": ["/say a", "/say b", "/say c", "/say d"],
            "phase": "spawn",
            "batchSize": 2,
            "meta": {
                "origin": "all",
                "dest": "vil",
                "boxes": 4,
                "bots": 4,
                "names": ["n1", "n2", "n3", "n4"],
            },
        },
    )
    assert start["ok"] is True, start
    run_id = start["data"]["runId"]

    status = {}
    # 300 × 10ms = 3s 的轮询预算；dry-run 的 command_interval=0.01s，足够跑完。
    for _ in range(300):
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status.get("waiting"):
            break
        time.sleep(0.01)

    assert status["waiting"] is True, status
    # 第 1 批（2 条）发完后必须停在闸门，日志给出「等待确认后继续下一批」。
    assert status["state"] == "running"
    assert status["batch"] == 1
    assert status["batches"] == 2
    assert status["sent"] == 2
    assert any("等待确认后继续下一批" in line for line in status["logs"])

    continued = api.tool_call("puppet", "run_continue", {"runId": run_id})
    assert continued["ok"] is True, continued
    assert continued["data"]["continued"] is True

    for _ in range(300):
        # 放行后第二批继续，最终状态应为 done。
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status["state"] != "running":
            break
        time.sleep(0.01)

    assert status["state"] == "done", status
    assert status["sent"] == 4
    assert status["waiting"] is False

    again = api.tool_call("puppet", "run_continue", {"runId": run_id})
    # 已结束的运单不再放行，重复调用是安全的 no-op。
    assert again["ok"] is True, again
    assert again["data"]["continued"] is False


def test_batch_run_can_be_stopped_while_waiting(api, monkeypatch):
    """验证在批间等待时也能被 run_stop 中断.

    输入：3 条命令、batchSize=1；第一批发完后调用 run_stop。
    期望：状态变为 aborted，sent=1（第二批不开始）。
    """
    import lspkit.tools.puppet.actions as puppet_actions

    monkeypatch.setattr(puppet_actions, "CommandRunner", _dry_runner)
    settings = api.settings_get("puppet")["data"]
    settings["allowExecute"] = True
    api.settings_save("puppet", settings)

    start = api.tool_call(
        "puppet",
        "run_start",
        {
            "commands": ["/say a", "/say b", "/say c"],
            "phase": "spawn",
            "batchSize": 1,
            "meta": {"origin": "all", "dest": "vil", "boxes": 3, "bots": 3},
        },
    )
    assert start["ok"] is True, start
    run_id = start["data"]["runId"]

    status = {}
    for _ in range(300):
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status.get("waiting"):
            break
        time.sleep(0.01)
    assert status["waiting"] is True, status

    assert api.tool_call("puppet", "run_stop", {"runId": run_id})["ok"] is True

    for _ in range(300):
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status["state"] != "running":
            break
        time.sleep(0.01)

    assert status["state"] == "aborted", status
    assert status["sent"] == 1


def test_draft_roundtrip(api):
    """验证订单草稿的默认值、保存与回读.

    输入：初始空草稿；保存 origin=all、dest=vil、boxes=250、operation=spawn_at_dest。
    期望：默认 operation=spawn_at_origin、boxes=0；保存后字段与 savedAt 都能读回。
    """
    empty = api.tool_call("puppet", "draft_load", {})["data"]["draft"]
    assert empty["origin"] == "" and empty["dest"] == ""
    assert empty["boxes"] == 0
    assert empty["operation"] == "spawn_at_origin"

    saved = api.tool_call(
        "puppet",
        "draft_save",
        {"origin": "all", "dest": "vil", "boxes": 250, "operation": "spawn_at_dest"},
    )
    assert saved["ok"] is True, saved

    draft = api.tool_call("puppet", "draft_load", {})["data"]["draft"]
    assert draft["origin"] == "all"
    assert draft["dest"] == "vil"
    assert draft["boxes"] == 250
    assert draft["operation"] == "spawn_at_dest"
    assert draft["savedAt"]


def test_draft_sanitizes_garbage(api):
    """验证草稿遇到脏数据时回落而不是报错.

    输入：boxes="abc"、operation="moon"。
    期望：boxes=0、operation=spawn_at_origin（草稿只是便利功能，坏了不挡下单）。
    """
    api.tool_call(
        "puppet",
        "draft_save",
        {"origin": "all", "dest": "vil", "boxes": "abc", "operation": "moon"},
    )
    draft = api.tool_call("puppet", "draft_load", {})["data"]["draft"]
    assert draft["boxes"] == 0
    assert draft["operation"] == "spawn_at_origin"
