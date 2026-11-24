"""Offline tests for the web UI backend. The orchestrator is replaced by a fake execute()."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from orchestra import orchestrator
from orchestra.state import AgentSpec
from server import create_app

TASK = {"task": "write hello.txt", "max_cost": 1}


def events(client, run_id):
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        body = "".join(r.iter_text())
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {\"")]


def wait_for(client, run_id, status, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get(f"/api/runs/{run_id}").json()
        if s["status"] == status and not s["active"]:
            return s
        time.sleep(0.02)
    raise AssertionError(f"run never reached {status}: {s}")


async def fake_execute(state):
    """Pretends to be the orchestrator: an agent, a passing task, a file, a finish."""
    await asyncio.sleep(0.05)
    state.agents["writer"] = AgentSpec("writer", "writes", "You write.", ["Write"])
    state.log("agent_created", name="writer", role="writes", tools=["Write"])
    state.record_usage(2, 0.1)
    (state.workspace / "hello.txt").write_text("hi")
    state.final_result = "done: hello.txt"
    state.status = "finished"
    orchestrator._wrap_up(state, "unused")
    return state


async def slow_execute(state):
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        state.status = "stopped"
        state.log("stopped")
        orchestrator._wrap_up(state, "stopped")
        raise


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "runs", execute=fake_execute)) as c:
        yield c


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Agent Orchestra" in r.text


def test_run_lifecycle(client):
    run_id = client.post("/api/runs", json=TASK).json()["id"]
    s = wait_for(client, run_id, "finished")
    assert s["final_result"] == "done: hello.txt" and "writer" in s["agents"]
    assert s["usage"]["cost_usd"] == pytest.approx(0.1)

    kinds = [e["event"] for e in events(client, run_id)]
    assert kinds[0] == "config" and kinds[-1] == "run_end"
    assert {"agent_created", "usage"} <= set(kinds)

    runs = client.get("/api/runs").json()
    assert runs[0]["id"] == run_id and runs[0]["status"] == "finished"


def test_live_stream_gets_events_after_subscribing(tmp_path):
    with TestClient(create_app(tmp_path / "runs", execute=fake_execute)) as c:
        run_id = c.post("/api/runs", json=TASK).json()["id"]
        evs = events(c, run_id)  # opened while running, must still end with run_end
        seqs = [e["seq"] for e in evs]
        assert evs[-1]["event"] == "run_end" and seqs == sorted(set(seqs))


def test_reconnect_skips_seen_events(client):
    run_id = client.post("/api/runs", json=TASK).json()["id"]
    wait_for(client, run_id, "finished")
    with client.stream("GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "2"}) as r:
        body = "".join(r.iter_text())
    seqs = [json.loads(l[6:])["seq"] for l in body.splitlines() if l.startswith("data: {\"")]
    assert seqs and min(seqs) == 3


def test_files_and_traversal(client, tmp_path):
    run_id = client.post("/api/runs", json=TASK).json()["id"]
    wait_for(client, run_id, "finished")
    files = client.get(f"/api/runs/{run_id}/files").json()["files"]
    assert [f["path"] for f in files] == ["hello.txt"]
    assert client.get(f"/api/runs/{run_id}/file", params={"path": "hello.txt"}).json()["content"] == "hi"
    (tmp_path / "secret.txt").write_text("nope")
    for bad in ["../../../secret.txt", "/etc/passwd", "../log.jsonl"]:
        assert client.get(f"/api/runs/{run_id}/file", params={"path": bad}).status_code == 404


def test_stop(tmp_path):
    with TestClient(create_app(tmp_path / "runs", execute=slow_execute)) as c:
        run_id = c.post("/api/runs", json=TASK).json()["id"]
        assert c.post(f"/api/runs/{run_id}/stop", json={}).json() == {"stopping": True}
        s = wait_for(c, run_id, "stopped")
        assert s["final_result"] == "stopped"
        assert c.post(f"/api/runs/{run_id}/stop", json={}).status_code == 409


def test_interrupted_run_shown_as_such(tmp_path):
    runs = tmp_path / "runs"
    (runs / "20250101-000000").mkdir(parents=True)
    (runs / "20250101-000000" / "board.json").write_text(json.dumps({"task": "x", "status": "running"}))
    with TestClient(create_app(runs, execute=fake_execute)) as c:
        assert c.get("/api/runs").json()[0]["status"] == "interrupted"


def test_bad_repo_rejected(client, tmp_path):
    r = client.post("/api/runs", json={**TASK, "repo": str(tmp_path)})
    assert r.status_code == 400 and "not a git repo" in r.json()["detail"]


def test_unknown_run_404(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/..%2F..").status_code == 404


def test_cross_site_requests_blocked(client):
    assert client.post("/api/runs", json=TASK, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/runs", headers={"Host": "evil.example"}).status_code == 403
    r = client.post("/api/runs", content=json.dumps(TASK), headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    assert client.post("/api/runs", json=TASK, headers={"Origin": "http://127.0.0.1:8000"}).status_code == 200
