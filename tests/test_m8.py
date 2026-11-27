"""M8 (teams and schedules): cron, the team store, memory, steering, triggers, room, webhook.

Offline: scripted runner and client, no model calls.
"""

import asyncio
import json
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from orchestra import fake
from orchestra.config import Config
from orchestra.orchestrator import create_run, execute_run
from orchestra.runner import AgentResult
from orchestra.state import RunState, read_events
from orchestra.tools import OrchestraTools
from server.app import create_app
from server.runs import RunManager
from server.teams import (PAST_HEADER, TeamError, TeamStore, clean_team, cron_matches, due_slots, parse_cron,
                          room_items)

CATALOG = ["files.read", "files.write", "web"]
TEAM = {"name": "Stocks desk", "goal": "Daily brief on my watchlist",
        "members": [{"name": "scout", "role": "Finds news", "tools": ["web", "files.write"], "tier": "haiku"},
                    {"name": "writer", "role": "Writes the brief", "tools": ["files.read", "files.write"]}],
        "schedule": [{"cron": "0 9 * * 1-5", "task": "Write today's brief"}]}


def run(coro):
    return asyncio.run(coro)


# ---- cron ------------------------------------------------------------------------------

def test_cron_matching():
    mon_9 = datetime(2026, 11, 30, 9, 0)          # a Monday
    assert cron_matches("0 9 * * 1-5", mon_9)
    assert not cron_matches("0 9 * * 0,6", mon_9)
    assert cron_matches("*/15 * * * *", mon_9.replace(minute=45))
    assert not cron_matches("*/15 * * * *", mon_9.replace(minute=50))
    assert cron_matches("0 9 30 11 *", mon_9)
    assert cron_matches("0 9 * * 7", datetime(2026, 11, 29, 9, 0))   # 7 = Sunday too
    for bad in ("0 9 * *", "61 * * * *", "* 25 * * *", "*/0 * * * *", "a b c d e"):
        with pytest.raises(ValueError):
            parse_cron(bad)


def test_due_slots_uses_team_time_zone():
    team = {"enabled": True, "timezone": "Asia/Jakarta", "schedule": [{"cron": "0 9 * * *", "task": "x"}]}
    # 09:00 in Jakarta (UTC+7) is 02:00 UTC
    from datetime import timezone
    ts = datetime(2026, 11, 30, 2, 0, tzinfo=timezone.utc).timestamp()
    assert due_slots(team, ts) == [(0, "2026-11-30T09:00")]
    assert due_slots({**team, "enabled": False}, ts) == []
    assert due_slots(team, ts + 60) == []


# ---- store and memory ----------------------------------------------------------------------

def test_clean_team_validates():
    with pytest.raises(TeamError, match="name"):
        clean_team({}, CATALOG)
    with pytest.raises(TeamError, match="unknown tools"):
        clean_team({"name": "x", "members": [{"name": "a", "tools": ["LaunchMissiles"]}]}, CATALOG)
    with pytest.raises(TeamError, match="tier"):
        clean_team({"name": "x", "members": [{"name": "a", "tier": "gpt"}]}, CATALOG)
    with pytest.raises(TeamError, match="Schedule"):
        clean_team({"name": "x", "schedule": [{"cron": "every day", "task": "t"}]}, CATALOG)
    with pytest.raises(TeamError, match="time zone"):
        clean_team({"name": "x", "timezone": "Mars/Olympus"}, CATALOG)
    with pytest.raises(TeamError, match="Two members"):
        clean_team({"name": "x", "members": [{"name": "a"}, {"name": "a"}]}, CATALOG)


def test_store_crud(tmp_path):
    st = TeamStore(tmp_path / "teams")
    t = st.create(TEAM, CATALOG)
    assert t["id"] == "stocks-desk" and t["hook"]["secret"] and PAST_HEADER in t["memory"]
    assert st.create(TEAM, CATALOG)["id"] != "stocks-desk"            # same name, new id
    up = st.update("stocks-desk", {"goal": "New goal", "memory": "## Notes\nno crypto\n"}, CATALOG)
    assert up["goal"] == "New goal" and "no crypto" in up["memory"]
    assert up["hook"]["secret"] == t["hook"]["secret"]                 # secret survives edits
    assert len(st.list()) == 2
    st.delete("stocks-desk")
    with pytest.raises(TeamError):
        st.get("stocks-desk")
    with pytest.raises(TeamError):
        st.get("../runs")


def test_memory_keeps_notes_and_trims_oldest_runs(tmp_path):
    st = TeamStore(tmp_path / "teams")
    st.create({**TEAM, "memory": f"## Notes\nno cooking videos\n\n{PAST_HEADER}\n"}, CATALOG)
    for i in range(60):
        st.remember_run("stocks-desk", f"Brief {i}", "x" * 300, "done")
    mem = st.get("stocks-desk")["memory"]
    assert "no cooking videos" in mem and "Brief 59" in mem and "Brief 0 " not in mem
    assert len(mem) <= 8000


# ---- steering ----------------------------------------------------------------------------

def make_tools(tmp_path):
    state = RunState("t", Config(), tmp_path)

    async def runner(*, prompt, output_schema=None, **kw):
        if output_schema:
            return AgentResult(text="", structured={"passed": True, "reason": "ok", "short": "ok"}, turns=1, cost_usd=0)
        return AgentResult(text="done", turns=1, cost_usd=0)
    t = OrchestraTools(state, runner=runner)
    run(t.create_agent({"name": "w", "role": "", "system_prompt": "", "tools": ["files.write"]}))
    run(t.assign_task({"agent": "w", "task_id": "t1", "title": "T", "task": "x", "done_when": "y"}))
    return state, t


def test_message_rides_along_with_next_tool_result(tmp_path):
    s, t = make_tools(tmp_path)
    s.steer("Also cover OVO please")
    res = run(t._with_messages(t.view_board)({}))
    assert "Also cover OVO please" in res["content"][-1]["text"]
    assert s.inbox == []
    assert run(t._with_messages(t.view_board)({}))["content"][-1]["text"].startswith("{")   # delivered once
    assert [e["text"] for e in read_events(s.run_dir) if e["type"] == "user_message"] == ["Also cover OVO please"]


def test_finish_waits_for_unread_messages(tmp_path):
    s, t = make_tools(tmp_path)
    s.steer("Wait, add a summary")
    res = run(t.finish({"result": "done"}))
    assert res.get("is_error") and "add a summary" in res["content"][0]["text"]
    assert s.final_result is None
    assert not run(t.finish({"result": "done"})).get("is_error")


def test_team_members_exist_before_the_orchestrator_starts(tmp_path):
    seen = {}

    class Client:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def query(self, prompt):
            seen["prompt"] = prompt
            seen["agents"] = list(state.agents)

        async def receive_response(self):
            await state.tools.assign_task({"agent": "scout", "task_id": "t1", "title": "T", "task": "x", "done_when": "y"})
            await state.tools.finish({"result": "ok"})
            from claude_agent_sdk import ResultMessage
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                                num_turns=1, session_id="s", total_cost_usd=0.0)

    team = {"id": "desk", "name": "Desk", "goal": "Briefs", "memory": "## Notes\nno crypto",
            "members": clean_team(TEAM, CATALOG)["members"]}
    state = create_run("Write the brief", Config(), tmp_path, team=team, trigger={"kind": "message"})
    run(execute_run(state, runner=make_tools(tmp_path / "x")[1].runner, catalog=fake.demo_catalog(),
                    client_factory=Client))
    assert seen["agents"] == ["scout", "writer"]
    assert "no crypto" in seen["prompt"] and "Your team: Desk" in seen["prompt"]
    started = read_events(state.run_dir)[0]
    assert started["team_id"] == "desk" and started["trigger"] == {"kind": "message"}
    assert json.loads((state.run_dir / "meta.json").read_text())["team_id"] == "desk"
    assert state.agents["scout"].model == "haiku"


# ---- server: triggers, room, webhook ---------------------------------------------------------

def wait(pred, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if (v := pred()):
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


def slow_script(gate):
    """A scripted orchestrator that waits for your message before finishing."""
    async def script(tools):
        await tools.assign_task({"agent": "scout", "task_id": "t1", "title": "Find news",
                                 "task": "[research] x", "done_when": "y"})
        yield "Working on it."
        for _ in range(200):
            if tools.s.inbox or gate.get("open"):
                break
            await asyncio.sleep(0.02)
        res = await tools.finish({"result": "Brief written."})
        if res.get("is_error"):
            yield "Got your message: " + res["content"][0]["text"][:200]
            await tools.finish({"result": "Brief written, with your change."})
    return script


@pytest.fixture
def team_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    gate = {}
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.0)
    mgr.client_factory = lambda options: fake.FakeClient(options, slow_script(gate),
                                                          {"state": next(iter(mgr.active.values())).state})
    with TestClient(create_app(mgr, web_dist=tmp_path / "nodist", schedule=False)) as c:
        c.gate = gate
        yield c


def test_team_api_crud_and_no_run_without_trigger(team_client):
    c = team_client
    r = c.post("/api/teams", json=TEAM)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert c.get("/api/teams").json()[0]["id"] == tid
    assert c.put(f"/api/teams/{tid}", json={"goal": "g"}).json()["goal"] == "g"
    assert c.post("/api/teams", json={"name": "x", "members": [{"name": "a", "tools": ["nope"]}]}).status_code == 400
    assert c.get("/api/runs").json()["runs"] == []                    # saving a team runs nothing
    assert c.delete(f"/api/teams/{tid}").status_code == 204
    assert c.get(f"/api/teams/{tid}").status_code == 404


def test_room_message_starts_a_run_then_steers_it(team_client):
    c = team_client
    tid = c.post("/api/teams", json=TEAM).json()["id"]
    first = c.post(f"/api/teams/{tid}/messages", json={"text": "Brief on BBCA today"}).json()
    assert first["steered"] is False
    rid = first["run_id"]
    wait(lambda: any(i["kind"] == "handoff" for i in c.get(f"/api/teams/{tid}/room").json()["items"]))
    second = c.post(f"/api/teams/{tid}/messages", json={"text": "Add BBRI too"}).json()
    assert second == {"run_id": rid, "steered": True}
    d = wait(lambda: (x := c.get(f"/api/runs/{rid}").json())["status"] == "finished" and x)
    assert "with your change" in d["final"]
    room = c.get(f"/api/teams/{tid}/room").json()["items"]
    kinds = [i["kind"] for i in room]
    assert kinds[0] == "you" and room[0]["text"] == "Brief on BBCA today"
    assert {"handoff", "result", "agent"} <= set(kinds)
    assert any(i["kind"] == "you" and i["text"] == "Add BBRI too" for i in room)
    mem = wait(lambda: PAST_HEADER in (m := c.get(f"/api/teams/{tid}").json()["memory"]) and "Brief on BBCA" in m and m)
    assert "done" in mem


def test_steer_endpoint_needs_a_running_run(team_client):
    assert team_client.post("/api/runs/nope/messages", json={"text": "hi"}).status_code == 409


def test_schedule_tick_fires_once_and_skips_when_busy(team_client):
    c = team_client
    tid = c.post("/api/teams", json={**TEAM, "timezone": "Asia/Jakarta",
                                     "schedule": [{"cron": "0 9 * * *", "task": "Morning brief"}]}).json()["id"]
    teams = c.app.state.teams
    from datetime import timezone
    nine = datetime(2026, 11, 30, 2, 0, tzinfo=timezone.utc).timestamp()   # 09:00 Jakarta
    portal = c.portal
    started = portal.call(teams.tick, nine)
    assert len(started) == 1
    assert portal.call(teams.tick, nine + 20) == []                       # same minute: not again
    assert portal.call(teams.tick, nine + 3600) == []                     # not due
    teams.fired.clear()
    assert portal.call(teams.tick, nine) == []                             # due, but the team is busy
    assert any(e["type"] == "trigger_skipped" for e in teams.store.events(tid))
    c.gate["open"] = True
    wait(lambda: c.get(f"/api/runs/{started[0]}").json()["status"] == "finished")
    room = c.get(f"/api/teams/{tid}/room").json()["items"]
    assert room[0]["kind"] == "system" and "Scheduled run" in room[0]["text"]
    assert any("Skipped" in i["text"] for i in room if i["kind"] == "system")


def test_webhook_needs_the_secret(team_client):
    c = team_client
    t = c.post("/api/teams", json={**TEAM, "hook": {"enabled": True, "task": "Check the new prices"}}).json()
    assert c.post(f"/api/hooks/{t['id']}/wrong", content=b"{}").status_code == 404
    r = c.post(f"/api/hooks/{t['id']}/{t['hook']['secret']}", content=b'{"BBCA": 9100}')
    assert r.status_code == 202
    rid = r.json()["run_id"]
    events = read_events(c.app.state.manager.runs_dir / rid)
    assert events[0]["trigger"] == {"kind": "webhook"} and "9100" in events[0]["task"]
    c.gate["open"] = True
    wait(lambda: c.get(f"/api/runs/{rid}").json()["status"] == "finished")


def test_webhook_disabled_is_not_found(team_client):
    c = team_client
    t = c.post("/api/teams", json=TEAM).json()
    assert c.post(f"/api/hooks/{t['id']}/{t['hook']['secret']}", content=b"{}").status_code == 404


def test_room_items_fold(tmp_path):
    s = RunState("Write it", Config(), tmp_path / "r1", trigger={"kind": "message"})
    s.log("run_started", task="Write it", title="Write it", trigger={"kind": "message"})
    s.log("orchestrator_said", text="On it")
    s.log("task_assigned", task_id="t1", title="Draft", agent="writer")
    s.log("user_message", text="shorter please")
    s.log("task_passed", task_id="t1", short="all good")
    s.log("finished", result="Done", give_up=False)
    items = room_items([{"t": 0, "type": "trigger_skipped", "what": "the 09:00 run", "why": "busy"}], [s.run_dir])
    assert [i["kind"] for i in items] == ["system", "you", "agent", "handoff", "you", "result", "agent"]
    assert items[3]["to"] == "writer" and items[5]["text"] == "Draft passed: all good" and items[6]["final"]


def test_demo_run_survives_a_mid_run_message(tmp_path):
    state = create_run(fake.DEMO_TASK, Config(), tmp_path)

    def on(e):
        if e["type"] == "task_passed" and e["task_id"] == "research-1":
            state.steer("Add a short summary at the top")
        if e["type"] == "approval_requested":
            asyncio.get_event_loop().call_soon(state.approvals.resolve, e["approval_id"], True)
    state.add_listener(on)
    run(execute_run(state, runner=fake.demo_runner(0), catalog=fake.demo_catalog(), interactive=True,
                    client_factory=fake.fake_client_factory(fake.demo_script, {"state": state})))
    assert state.status == "finished"
    said = [e["text"] for e in read_events(state.run_dir) if e["type"] == "orchestrator_said"]
    assert any("Got your message" in t for t in said)


def test_tiktok_team_demo_in_the_room(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_TOKEN", raising=False)
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.0)
    with TestClient(create_app(mgr, web_dist=tmp_path / "x", schedule=False)) as c:
        tid = c.post("/api/teams", json={"name": "TikTok studio", "goal": "Student life videos",
                                         "members": fake.TIKTOK_MEMBERS}).json()["id"]
        rid = c.post(f"/api/teams/{tid}/messages", json={"text": "Make 3 videos for this week"}).json()["run_id"]
        c.post(f"/api/teams/{tid}/messages", json={"text": "No cooking videos please"})
        ap = wait(lambda: next((i for i in c.get(f"/api/teams/{tid}/room").json()["items"] if i["kind"] == "approval"), None))
        assert ap["from"] == "poster" and ap["run_id"] == rid
        assert c.post(f"/api/runs/{rid}/approvals/{ap['approval_id']}", json={"decision": "approve"}).status_code == 200
        d = wait(lambda: (x := c.get(f"/api/runs/{rid}").json())["status"] == "finished" and x)
        assert "No cooking" in d["final"]
        room = c.get(f"/api/teams/{tid}/room").json()["items"]
        assert any(i["kind"] == "system" and i["text"] == "Approved: schedule posts" and i["approval_id"] == ap["approval_id"]
                   for i in room)
        assert any(i["kind"] == "agent" and "cooking" in i["text"] for i in room)           # the reply to your message
        assert {i["to"] for i in room if i["kind"] == "handoff"} >= {"trendscout", "analyst", "scriptwriter", "editor", "poster"}
