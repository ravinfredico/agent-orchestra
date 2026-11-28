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


# ---- 9.3 stocks team: never trades, briefs say "Not financial advice" ------------------------

def test_stocks_proposal_has_no_trading_and_a_fixed_rule():
    p = builder.clean_proposal(fake.demo_proposal("A team for stocks on my watchlist"), CAT)
    team = p["team"]
    assert team["name"] == "Stocks desk" and "Never trades" in team["goal"]
    assert all(builder.FINANCE_RULE in m["system_prompt"] for m in team["members"])
    analyst = next(m for m in team["members"] if m["name"] == "analyst")
    assert analyst["wants"] == ["market-data.prices"]                      # missing data API: a setup step
    assert {s["kind"] for s in p["setup"]} == {"missing_tool"}
    assert team["hook"]["enabled"] and "3%" in team["hook"]["task"]          # alerts come in on the webhook
    assert p["approvals"] == [] and p["refused"] == []


def test_money_tools_are_refused_even_if_the_model_asks():
    raw = {"name": "Trader", "goal": "Watch my portfolio", "members": [{"name": "bot", "role": "r", "tier": "haiku",
           "tools": ["web", "broker.orders", "connector.Trading 212", "payments", "files.write"]}]}
    p = builder.clean_proposal(raw, CAT)
    m = p["team"]["members"][0]
    assert m["tools"] == ["web", "files.write"] and m["wants"] == []
    assert p["refused"] == ["broker.orders", "connector.trading-212", "connector.payments"]
    assert builder.FINANCE_RULE in m["system_prompt"]


def test_non_finance_teams_get_no_finance_rule():
    p = builder.clean_proposal(fake.demo_proposal("marketing"), CAT)
    assert not any(builder.FINANCE_RULE in m["system_prompt"] for m in p["team"]["members"])


def test_no_trading_tool_in_any_catalog():
    from orchestra.catalog import load_catalog
    for cat in (load_catalog(), CAT):
        assert not [e.id for e in cat.entries if builder.MONEY_TOOL.search(e.id)]


def test_stocks_team_demo_brief_never_advises(client):
    p = client.post("/api/teams/propose", json={"goal": "I want a team for stocks"}).json()
    tid = client.post("/api/teams", json=p["team"]).json()["id"]
    rid = client.post(f"/api/teams/{tid}/messages", json={"text": "Write today's brief"}).json()["run_id"]
    d = wait(lambda: (x := client.get(f"/api/runs/{rid}").json())["status"] == "finished" and x)
    assert d["final"].endswith("Not financial advice.")
    from orchestra.state import read_events
    events = read_events(client.app.state.teams.manager.run_dir(rid))
    failed = [e for e in events if e["type"] == "attempt_failed"]
    assert failed and "buy BBRI" in failed[0]["reason"]                     # the checker caught the advice
    brief = client.get(f"/api/runs/{rid}/files/brief-2026-11-30.md").text
    assert "Not financial advice" in brief and "buy" not in brief.lower()
    room = client.get(f"/api/teams/{tid}/room").json()["items"]
    assert {i["to"] for i in room if i["kind"] == "handoff"} == {"scout", "analyst", "writer"}


def test_fake_runner_checks_unscripted_work_without_crashing(tmp_path):
    r = fake.FakeRunner({"[known]": fake.FakeTask()})
    run(r(prompt="[other] x", cwd=tmp_path))
    res = run(r(prompt="[other] x", output_schema={"type": "object"}))
    assert res.structured["passed"] is True


# ---- M10 video studio: parsing the cards the team writes -----------------------------------

def test_studio_card_parsing():
    from server.studio import parse_card
    c = parse_card("# Kos tour\n\nHook (0-2 s): look\n\nCaption: Would you live here? #fyp\n\n#anakkos #depok", "01-kos")
    assert c == {"title": "Kos tour", "caption": "Would you live here?", "hashtags": ["#fyp", "#anakkos", "#depok"]}
    assert parse_card("", "02-krl-rush")["title"] == "02 krl rush"
    assert parse_card("Just a caption line\n#a #b", "x")["caption"] == "Just a caption line"


def test_studio_items_pair_files_and_skip_odd_names(tmp_path):
    from server import studio
    ws = tmp_path / "r1" / "workspace" / "videos"
    ws.mkdir(parents=True)
    (ws / "a.md").write_text("# A\nCaption: hi")
    (ws / "a.mp4").write_bytes(b"x")
    (ws / "b.mp4").write_bytes(b"x")                  # video without a card
    (ws / ".hidden.md").write_text("# no")
    items = studio.items([tmp_path / "r1"], lambda rid: tmp_path / rid / "workspace", {"r1/a": 1.0})
    by = {i["name"]: i for i in items}
    assert set(by) == {"a", "b"}
    assert by["a"]["video"] == "videos/a.mp4" and by["a"]["posted_at"] == 1.0
    assert by["b"]["script"] is None and by["b"]["title"] == "b"
    marks = studio.set_posted(tmp_path, "r1/b", 2.0)
    assert studio.load_posted(tmp_path) == marks == {"r1/b": 2.0}
    assert studio.set_posted(tmp_path, "r1/b", None) == {}
