import json

from orchestra.config import Config
from orchestra.state import RunState, auth_mode, make_run_id, read_events


def test_run_ids_unique():
    ids = {make_run_id() for _ in range(200)}
    assert len(ids) == 200


def test_envelope_and_listeners(tmp_path):
    got = []
    s = RunState("task", Config(), tmp_path / "r1", listeners=[got.append])
    s.log("run_started", task="task")
    s.log("orchestrator_said", text="hi")
    raw = (s.run_dir / "log.jsonl").read_text()
    assert "\033" not in raw
    ev = read_events(s.run_dir)
    assert [e["seq"] for e in ev] == [1, 2] and ev[0]["run_id"] == "r1"
    assert got == ev
    assert read_events(s.run_dir, after=1) == ev[1:]


def test_broken_listener_does_not_stop_run(tmp_path):
    def bad(e):
        raise ValueError("boom")
    s = RunState("t", Config(), tmp_path, listeners=[bad])
    s.log("run_started")
    assert s.status == "running"


def test_status_tracking(tmp_path):
    s = RunState("t", Config(), tmp_path)
    s.log("finished", give_up=True)
    assert s.status == "gave_up"


def test_auth_mode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert auth_mode() == "plan"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-for-test")
    assert auth_mode() == "api_key"


def test_meta_written(tmp_path):
    s = RunState("my task", Config(), tmp_path, repo="/r", branch="orchestra/x", parent_id="p")
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["branch"] == "orchestra/x" and meta["parent_id"] == "p" and meta["options"]["max_cost"] == 5.0
