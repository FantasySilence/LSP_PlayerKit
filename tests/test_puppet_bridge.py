# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货 API 契约        #
# =================================== #

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

    def __init__(self, config=None, logger=None, on_progress=None):
        _FakeRunner.last_config = config
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
