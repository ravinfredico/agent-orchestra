"""Server tests: FastAPI TestClient + the scripted demo runner. No model calls."""

import json
import subprocess
import time
import zipfile
import io

import pytest
from fastapi.testclient import TestClient

from orchestra import fake
from server.app import create_app
from server.runs import RunManager


def wait_done(c, run_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        d = c.get(f"/api/runs/{run_id}").json()
        if d["status"] not in ("running", "created"):
            return d
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def auto_approve(c, run_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        d = c.get(f"/api/runs/{run_id}").json()
        if d["pending_approvals"]:
            ap = d["pending_approvals"][0]["approval_id"]
            assert c.post(f"/api/runs/{run_id}/approvals/{ap}", json={"decision": "approve"}).status_code == 200
            return ap
        if d["status"] != "running":
            return None
        time.sleep(0.02)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.0)
    with TestClient(create_app(mgr, web_dist=tmp_path / "nodist")) as c:
        yield c


def test_health_and_catalog(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["auth_mode"] in ("plan", "api_key") and h["fake_mode"]
    cat = client.get("/api/catalog").json()
    ids = {e["id"] for e in cat}
    assert "gmail" in ids and all("server" not in e for e in cat)


def test_full_demo_run(client):
    r = client.post("/api/runs", json={"task": fake.DEMO_TASK, "options": {"max_cost": 5}})
    assert r.status_code == 201
    run_id = r.json()["id"]
    assert auto_approve(client, run_id)                          # the editor's email needs approval
    d = wait_done(client, run_id)
    assert d["status"] == "finished" and d["tasks_total"] == 4 and d["tasks_passed"] == 3
    board = {b["task_id"]: b for b in d["board"]}
    assert board["report-1"]["status"] == "replaced" and board["report-1"]["replaced_by"] == "report-2"
    assert board["analysis-1"]["history"][0]["short"] == "2 wallets missing fees"
    assert [a["color_index"] for a in d["agents"]] == [0, 1, 2, 3]

    # history list + search
    runs = client.get("/api/runs").json()["runs"]
    assert runs[0]["id"] == run_id and runs[0]["status"] == "finished"
    assert client.get("/api/runs", params={"q": "wallets"}).json()["runs"]
    assert not client.get("/api/runs", params={"q": "zebra"}).json()["runs"]
    assert client.get("/api/runs", params={"status": "finished"}).json()["runs"]

    # SSE replay of a finished run: every event in order, then end
    with client.stream("GET", f"/api/runs/{run_id}/events") as s:
        body = "".join(s.iter_text())
    ids = [int(line[4:]) for line in body.splitlines() if line.startswith("id: ")]
    assert ids == list(range(1, len(ids) + 1)) and "event: end" in body
    with client.stream("GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(len(ids) - 2)}) as s:
        body2 = "".join(s.iter_text())
    assert [int(l[4:]) for l in body2.splitlines() if l.startswith("id: ")] == ids[-2:]

    # files
    files = client.get(f"/api/runs/{run_id}/files").json()
    paths = [f["path"] for f in files]
    assert "report.md" in paths and not any(p.startswith(".agents") for p in paths)
    assert next(f for f in files if f["path"] == "report.md")["agent"] == "editor"
    assert client.get(f"/api/runs/{run_id}/files/report.md").text.startswith("# Indonesian")
    assert client.get(f"/api/runs/{run_id}/files/../meta.json").status_code in (400, 404)
    assert client.get(f"/api/runs/{run_id}/files/%2E%2E/meta.json").status_code in (400, 404)
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/zip").content))
    assert "report.md" in z.namelist()

    # follow-up copies the workspace
    r2 = client.post("/api/runs", json={"task": "Translate the report", "parent": {"run_id": run_id, "mode": "follow_up"}})
    assert r2.status_code == 201
    child = client.get(f"/api/runs/{r2.json()['id']}").json()
    assert child["parent_id"] == run_id
    auto_approve(client, child["id"])
    wait_done(client, child["id"])

    # delete
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_stop(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.2)
    with TestClient(create_app(mgr, web_dist=tmp_path / "x")) as c:
        run_id = c.post("/api/runs", json={"task": "slow"}).json()["id"]
        time.sleep(0.3)
        assert c.delete(f"/api/runs/{run_id}").status_code == 409     # can't delete while running
        t0 = time.time()
        assert c.post(f"/api/runs/{run_id}/stop").status_code == 202
        d = wait_done(c, run_id)
        assert d["status"] == "stopped" and time.time() - t0 < 5
        # continue from the stopped run
        r = c.post(f"/api/runs/{run_id}/continue", json={"extra_budget_usd": 3})
        assert r.status_code == 201
        child = c.get(f"/api/runs/{r.json()['id']}").json()
        assert child["parent_id"] == run_id and child["options"]["max_cost"] == 3
        c.post(f"/api/runs/{child['id']}/stop")


def test_parallel_runs_and_status(client):
    ids = [client.post("/api/runs", json={"task": f"run {i}"}).json()["id"] for i in range(3)]
    assert len(set(ids)) == 3
    st = client.get("/api/status").json()
    assert "running" in st
    for i in ids:
        auto_approve(client, i)
        assert wait_done(client, i)["status"] == "finished"
    assert client.get("/api/status").json()["last"]["status"] == "finished"


def test_bad_requests(client):
    assert client.post("/api/runs", json={"task": "  "}).status_code == 400
    assert client.post("/api/runs/nope/stop").status_code == 409
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fetc").status_code == 404
    assert client.post("/api/runs/x/approvals/y", json={"decision": "maybe"}).status_code == 400


def test_recovery_marks_interrupted(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    d = tmp_path / "runs" / "20260101-000000-abcd"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"task": "old", "title": "old", "created_at": 1.0}))
    (d / "log.jsonl").write_text(json.dumps({"seq": 1, "run_id": d.name, "t": 1.0, "type": "run_started"}) + "\n")
    with TestClient(create_app(RunManager(tmp_path / "runs", fake_mode=True), web_dist=tmp_path / "x")) as c:
        r = c.get(f"/api/runs/{d.name}").json()
        assert r["status"] == "interrupted"
        assert c.get("/api/runs").json()["runs"][0]["status"] == "interrupted"


def test_auth_token(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_TOKEN", "test-token-123")
    with TestClient(create_app(RunManager(tmp_path / "runs", fake_mode=True), web_dist=tmp_path / "x")) as c:
        assert c.get("/api/health").status_code == 200                 # health is open
        assert c.get("/api/runs").status_code == 401
        assert c.get("/api/runs", headers={"Authorization": "Bearer test-token-123"}).status_code == 200
        assert c.post("/api/login", json={"token": "wrong"}).status_code == 401
        assert c.post("/api/login", json={"token": "test-token-123"}).status_code == 200
        assert c.get("/api/runs").status_code == 200                   # cookie now set


def test_host_guard(monkeypatch):
    from server.auth import check_host
    monkeypatch.delenv("APP_TOKEN", raising=False)
    check_host("127.0.0.1")
    with pytest.raises(SystemExit):
        check_host("0.0.0.0")


def test_repo_conflict_and_allowlist(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    repo = tmp_path / "repos" / "app"
    repo.mkdir(parents=True)
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "a.py").write_text("x=1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "i"], check=True)
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.2, repos_root=str(tmp_path / "repos"))
    with TestClient(create_app(mgr, web_dist=tmp_path / "x")) as c:
        assert c.post("/api/runs", json={"task": "x", "options": {"repo": str(tmp_path)}}).status_code == 400
        r = c.post("/api/runs", json={"task": "x", "options": {"repo": str(repo)}})
        assert r.status_code == 201
        assert c.get(f"/api/runs/{r.json()['id']}").json()["branch"].startswith("orchestra/")
        assert c.post("/api/runs", json={"task": "y", "options": {"repo": str(repo)}}).status_code == 409
        c.post(f"/api/runs/{r.json()['id']}/stop")
