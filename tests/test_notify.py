"""ntfy notifications and the .env loader. Offline: pushes go to a recording fake."""

import time

from fastapi.testclient import TestClient

from orchestra.envfile import load_env
from server import notify
from server.app import create_app
from server.runs import RunManager


def test_messages_for_each_event():
    done = notify.message_for({"type": "finished", "result": "Built todo.py with 11 passing tests."}, "Build a todo app")
    assert done["title"] == "Done: Build a todo app" and "11 passing" in done["message"]
    out = notify.message_for({"type": "finished", "give_up": True, "result": "2 of 4 tasks passed"}, "Report")
    assert out["title"].startswith("Out of budget") and out["priority"] == notify.PRIORITY["default"]
    crash = notify.message_for({"type": "run_failed", "kind": "auth", "hint": "Run claude, then /login"}, "Report")
    assert crash["title"] == "Claude login expired: Report" and crash["priority"] == notify.PRIORITY["high"]
    ask = notify.message_for({"type": "approval_requested", "agent": "editor", "tool": "mcp__gmail__send_message"}, "Report")
    assert ask["message"].startswith("editor wants to send message") and ask["priority"] == notify.PRIORITY["high"]


def test_quiet_events_send_nothing():
    for t in ("task_passed", "attempt_failed", "usage", "worker_activity", "run_stopped", "agent_created"):
        assert notify.message_for({"type": t}, "x") is None


def test_long_results_are_shortened():
    m = notify.message_for({"type": "finished", "result": "word " * 200}, "x")
    assert len(m["message"]) <= 180 and m["message"].endswith("…")


def test_notifier_posts_json_with_a_link_to_the_run():
    sent = []
    n = notify.Notifier("https://ntfy.example/", "chacha-topic", "https://pa.example.com/", token="tk",
                        title_of=lambda rid: "My run", post=lambda url, body, token: sent.append((url, body, token)),
                        background=False)
    n({"type": "task_passed", "run_id": "r1"})
    n({"type": "finished", "run_id": "r1", "result": "ok"})
    assert len(sent) == 1
    url, body, token = sent[0]
    assert url == "https://ntfy.example" and token == "tk"
    assert body["topic"] == "chacha-topic" and body["title"] == "Done: My run"
    assert body["click"] == "https://pa.example.com/runs/r1"


def test_off_unless_url_and_topic_are_set():
    assert notify.from_env(env={}) is None
    assert notify.from_env(env={"NTFY_URL": "https://ntfy.sh"}) is None
    n = notify.from_env(env={"NTFY_URL": "https://ntfy.sh", "NTFY_TOPIC": "t"})
    assert n and n.public_url == "http://127.0.0.1:8000" and n.token is None


def test_server_run_sends_a_push_when_it_finishes(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    sent = []
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.0)
    mgr.notify = notify.Notifier("https://ntfy.example", "t", title_of=mgr.title_of,
                                 post=lambda url, body, token: sent.append(body), background=False)
    with TestClient(create_app(mgr, web_dist=tmp_path / "nodist")) as c:
        rid = c.post("/api/runs", json={"task": "Build a Python CLI todo app with pytest tests that all pass",
                                        "options": {"allow_bash": True}}).json()["id"]
        end = time.time() + 10
        while time.time() < end and not sent:
            time.sleep(0.05)
    assert [b["title"] for b in sent] == [f"Done: {mgr.title_of(rid)}"]
    assert sent[0]["click"].endswith(f"/runs/{rid}")


def test_load_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nNTFY_URL=https://ntfy.sh\nexport NTFY_TOPIC="abc"\nEMPTY=\nKEEP=from-file\n'
                 "ANTHROPIC_API_KEY=sk-should-not-load\n")
    env = {"KEEP": "from-shell"}
    assert sorted(load_env(f, env)) == ["NTFY_TOPIC", "NTFY_URL"]
    assert env == {"KEEP": "from-shell", "NTFY_URL": "https://ntfy.sh", "NTFY_TOPIC": "abc"}
    assert load_env(tmp_path / "missing", env) == []
