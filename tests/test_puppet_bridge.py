# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货 API 契约        #
# =================================== #

import time

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
    result = api.tool_call("puppet", "stations_save", {"station": station})
    assert result["ok"] is True, result
    return result["data"]


def test_puppet_is_registered(api):
    ids = [tool["id"] for tool in api.app_state()["data"]["tools"]]
    assert "puppet" in ids
    assert ids.index("material") < ids.index("puppet")


def test_stations_roundtrip(api):
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
    result = api.tool_call("puppet", "stations_save", {"station": {**STATION, "dimension": "moon"}})
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_STATION"


def test_plan_via_api(api):
    save_station(api, STATION)
    save_station(api, DEST)

    result = api.tool_call(
        "puppet", "plan", {"origin": "all", "dest": "vil", "boxes": 250}
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["bots"] == 7
    assert data["waves"] == 1
    assert data["commands"][0]["text"].startswith("/execute in minecraft:overworld")
    assert data["estimate"]["spawnSeconds"] > 0
    assert data["spawnStation"]["group"] == "重溟洋工业区"
    assert data["spawnStation"]["name"] == "全物品"


def test_plan_rejects_same_station(api):
    save_station(api, STATION)
    result = api.tool_call(
        "puppet", "plan", {"origin": "all", "dest": "all", "boxes": 1}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PLAN"


def test_plan_unknown_station(api):
    result = api.tool_call(
        "puppet", "plan", {"origin": "nope", "dest": "nope", "boxes": 1}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "STATION_NOT_FOUND"


def test_execute_disabled_by_default(api):
    result = api.tool_call(
        "puppet",
        "run_start",
        {"commands": ["/say hi"], "phase": "spawn", "meta": {}},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "EXECUTE_DISABLED"


def test_stations_import(api):
    text = "永夜岛工业区·混凝土工厂 136 48 8 end_concrete\n"
    result = api.tool_call(
        "puppet", "stations_import", {"text": text, "defaultDimension": "the_end"}
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["added"] == 1
    assert data["stations"][0]["prefix"] == "concrete"
    assert data["stations"][0]["dimension"] == "the_end"


def test_stations_export_json_roundtrip(api):
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
    save_station(api, STATION)
    save_station(api, DEST)

    payload = api.tool_call("puppet", "stations_export", {"format": "text"})["data"]
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
    result = api.tool_call("puppet", "stations_export", {})
    assert result["ok"] is False
    assert result["error"]["code"] == "NO_STATIONS"


def test_history_clear(api):
    assert api.tool_call("puppet", "history_clear", {})["data"]["orders"] == []
    assert api.tool_call("puppet", "history_list", {})["data"]["orders"] == []


def test_diagnose_shape(api):
    data = api.tool_call("puppet", "diagnose", {})["data"]
    assert "supported" in data and isinstance(data["checks"], list)


class _FakeRunner:
    """只验证线程 / 状态 / 台账链路，不碰真实键盘."""

    last_config = None
    last_kwargs: dict = {}

    def __init__(self, config=None, logger=None, on_progress=None, **kwargs):
        _FakeRunner.last_config = config
        _FakeRunner.last_kwargs = kwargs
        self.logger = logger
        self.on_progress = on_progress

    def run(self, commands):
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
    import time

    import lspkit.tools.puppet.actions as puppet_actions

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
    assert _FakeRunner.last_config.final_message == "Operation completed successfully"
    assert _FakeRunner.last_kwargs["batch_size"] == 0
    assert _FakeRunner.last_kwargs["batch_gate"] is None


class _QuietTransport:
    """dry-run 用的假 Transport：只提供虚拟时钟与空按键状态."""

    def __init__(self):
        self.time = 0.0
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
    for _ in range(300):
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status.get("waiting"):
            break
        time.sleep(0.01)

    assert status["waiting"] is True, status
    assert status["state"] == "running"
    assert status["batch"] == 1
    assert status["batches"] == 2
    assert status["sent"] == 2
    assert any("等待确认后继续下一批" in line for line in status["logs"])

    continued = api.tool_call("puppet", "run_continue", {"runId": run_id})
    assert continued["ok"] is True, continued
    assert continued["data"]["continued"] is True

    for _ in range(300):
        status = api.tool_call("puppet", "run_status", {"runId": run_id})["data"]
        if status["state"] != "running":
            break
        time.sleep(0.01)

    assert status["state"] == "done", status
    assert status["sent"] == 4
    assert status["waiting"] is False

    again = api.tool_call("puppet", "run_continue", {"runId": run_id})
    assert again["ok"] is True, again
    assert again["data"]["continued"] is False


def test_batch_run_can_be_stopped_while_waiting(api, monkeypatch):
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
    api.tool_call(
        "puppet",
        "draft_save",
        {"origin": "all", "dest": "vil", "boxes": "abc", "operation": "moon"},
    )
    draft = api.tool_call("puppet", "draft_load", {})["data"]["draft"]
    assert draft["boxes"] == 0
    assert draft["operation"] == "spawn_at_origin"
