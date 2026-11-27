"""M9 (team builder): proposals, missing tools as setup steps, approvals, the marketing demo.

Offline: scripted runner, demo catalog, no model calls.
"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from orchestra import builder, fake
from orchestra.runner import AgentResult
from server.app import create_app
from server.runs import RunManager


def run(coro):
    return asyncio.run(coro)


def wait(pred, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if (v := pred()):
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


CAT = fake.demo_catalog(connectors=True)   # Figma and Notion connected, Slack needs sign-in, no Gmail


def test_marketing_proposal_shape():
    p = builder.clean_proposal(fake.demo_proposal("I want a marketing team"), CAT)
    team = p["team"]
    assert [m["name"] for m in team["members"]] == ["strategist", "copywriter", "designer", "coordinator"]
    assert {m["tier"] for m in team["members"]} <= {"haiku", "sonnet"}
    assert len(team["schedule"]) == 2 and team["outputs"] and p["questions"][0]["options"]
    coord = team["members"][3]
    assert "connector.slack" in coord["tools"] and coord["wants"] == ["connector.gmail"]


def test_missing_tools_become_setup_steps_never_tools():
    raw = {"name": "Stocks", "goal": "g", "summary": "s", "schedule": [], "outputs": [], "questions": [],
           "members": [{"name": "Scout", "role": "r", "tier": "haiku",
                        "tools": ["web", "Gmail", "connector.Google Drive", "marketdata.api", "files.write"]}]}
    p = builder.clean_proposal(raw, CAT)
    m = p["team"]["members"][0]
    assert m["name"] == "scout" and m["tools"] == ["web", "files.write"]
    assert m["wants"] == ["connector.gmail", "connector.google-drive", "marketdata.api"]
    kinds = {s["tool"]: s["kind"] for s in p["setup"]}
    assert kinds == {"connector.gmail": "connect", "connector.google-drive": "connect", "marketdata.api": "missing_tool"}
    assert any("Connect Gmail at claude.ai" in s["text"] for s in p["setup"])
    assert not any(e.id in m["wants"] for e in CAT.entries)   # nothing was added to the catalog


def test_known_connector_names_map_to_catalog_ids():
    raw = {"name": "x", "members": [{"name": "a", "role": "r", "tier": "opus", "tools": ["Figma", "connector.Notion"]}]}
    m = builder.clean_proposal(raw, CAT)["team"]["members"][0]
    assert m["tools"] == ["connector.figma", "connector.notion"] and m["wants"] == []
    assert m["tier"] == "sonnet"   # proposals never pick opus


def test_approvals_and_sign_in_come_from_the_catalog():
    p = builder.clean_proposal(fake.demo_proposal("marketing"), CAT)
    assert any(a.startswith("designer asks") and "Figma" in a for a in p["approvals"])
    assert any(a.startswith("coordinator asks") and "Slack" in a for a in p["approvals"])
    assert not any(a.startswith("copywriter") for a in p["approvals"])   # files only: never asks
    slack = next(s for s in p["setup"] if s["tool"] == "connector.slack")
    assert slack["kind"] == "sign_in" and "/mcp" in slack["text"]


def test_bad_answers():
    with pytest.raises(ValueError):
        builder.clean_proposal({"name": "x", "members": []}, CAT)
    with pytest.raises(ValueError):
        builder.clean_proposal("not json", CAT)
    raw = {"name": "x", "members": [{"name": "a", "role": "r", "tier": "haiku", "tools": []}],
           "schedule": [{"cron": "every day", "task": "t"}, {"cron": "0 9 * * *", "task": "ok"}]}
    assert builder.clean_proposal(raw, CAT)["team"]["schedule"] == [{"cron": "0 9 * * *", "task": "ok"}]


def test_propose_makes_one_cheap_call_without_tools():
    calls = []

    async def runner(**kw):
        calls.append(kw)
        return AgentResult(text="", structured=fake.demo_proposal("marketing"), turns=1, cost_usd=0.02)

    p = run(builder.propose("I want a marketing team", CAT, runner=runner))
    assert len(calls) == 1 and calls[0]["tools"] == [] and calls[0]["model"] == "sonnet"
    assert calls[0]["env"] == {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
    assert "connector.figma" in calls[0]["system_prompt"] and p["cost_usd"] == 0.02
    with pytest.raises(ValueError):
        run(builder.propose("  ", CAT, runner=runner))


def test_propose_reports_a_failed_call():
    async def runner(**kw):
        return AgentResult(text="", is_error=True, error="rate limited")
    with pytest.raises(ValueError, match="rate limited"):
        run(builder.propose("a team", CAT, runner=runner))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.0)
    with TestClient(create_app(mgr, web_dist=tmp_path / "nodist", schedule=False)) as c:
        yield c


def test_propose_endpoint_then_save_keeps_wants_and_setup(client):
    assert client.post("/api/teams/propose", json={"goal": ""}).status_code == 400
    p = client.post("/api/teams/propose", json={"goal": "I want a marketing team"}).json()
    assert p["team"]["name"] == "Marketing team" and client.get("/api/teams").json() == []   # nothing saved
    saved = client.post("/api/teams", json=p["team"]).json()
    assert saved["outputs"] == p["team"]["outputs"]
    assert saved["members"][3]["wants"] == ["connector.gmail"]
    assert {s["service"] for s in saved["setup"]} == {"Slack", "Gmail"}
    assert any("Figma" in a for a in saved["approvals"])


def test_marketing_team_demo_run_asks_before_figma(client):
    p = client.post("/api/teams/propose", json={"goal": "I want a marketing team"}).json()
    tid = client.post("/api/teams", json=p["team"]).json()["id"]
    rid = client.post(f"/api/teams/{tid}/messages", json={"text": "Plan this week's posts"}).json()["run_id"]
    ap = wait(lambda: next((i for i in client.get(f"/api/teams/{tid}/room").json()["items"] if i["kind"] == "approval"), None))
    assert ap["from"] == "designer" and "use figma" in ap["text"]
    client.post(f"/api/runs/{rid}/approvals/{ap['approval_id']}", json={"decision": "approve"})
    d = wait(lambda: (x := client.get(f"/api/runs/{rid}").json())["status"] == "finished" and x)
    assert "Week 48" in d["final"]
    agents = {a["name"]: a for a in d["agents"]} if isinstance(d.get("agents"), list) else d["agents"]
    # Slack needs sign-in and Gmail isn't connected: the coordinator runs without them
    assert set(agents) >= {"strategist", "copywriter", "designer", "coordinator"}
    coord_tools = agents["coordinator"]["tools"]
    assert "connector.slack" not in coord_tools and "connector.gmail" not in coord_tools
