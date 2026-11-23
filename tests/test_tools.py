"""Offline tests for the orchestration logic. No model calls: the runner is faked.

    python -m pytest tests -q
"""

import asyncio
import json

from orchestra.config import Budget, Config
from orchestra.runner import AgentResult
from orchestra.state import RunState
from orchestra.tools import OrchestraTools


def make(tmp_path, verdicts, budget=None):
    """verdicts: list of bools the fake checker returns, in order."""
    state = RunState("demo task", Config(budget=budget or Budget()), tmp_path)
    calls = {"worker": 0, "checker": 0, "prompts": []}
    it = iter(verdicts)

    async def fake_runner(*, prompt, output_schema=None, **kw):
        if output_schema:  # checker
            calls["checker"] += 1
            ok = next(it)
            return AgentResult(text="", structured={"passed": ok, "reason": "ok" if ok else "missing file"},
                               turns=1, cost_usd=0.1)
        calls["worker"] += 1
        calls["prompts"].append(prompt)
        return AgentResult(text="wrote report.md", turns=3, cost_usd=0.2)

    return state, OrchestraTools(state, runner=fake_runner), calls


def run(coro):
    return asyncio.run(coro)


def text(res):
    return res["content"][0]["text"]


AGENT = {"name": "writer", "role": "writes", "system_prompt": "You write.", "tools": ["Read", "Write"]}
TASK = {"agent": "writer", "task_id": "t1", "task": "write report.md", "done_when": "report.md exists"}


def test_create_agent_rejects_unknown_tool(tmp_path):
    _, t, _ = make(tmp_path, [])
    res = run(t.create_agent({**AGENT, "tools": ["Read", "LaunchMissiles"]}))
    assert res.get("is_error") and "Unknown tools" in text(res)


def test_bash_only_when_allowed(tmp_path):
    _, t, _ = make(tmp_path, [])
    assert run(t.create_agent({**AGENT, "tools": ["Bash"]})).get("is_error")


def test_agent_limit(tmp_path):
    _, t, _ = make(tmp_path, [], Budget(max_agents=1))
    run(t.create_agent(AGENT))
    res = run(t.create_agent({**AGENT, "name": "second"}))
    assert res.get("is_error") and "limit" in text(res)


def test_pass_first_try(tmp_path):
    s, t, calls = make(tmp_path, [True])
    run(t.create_agent(AGENT))
    res = run(t.assign_task(TASK))
    assert "PASSED on attempt 1" in text(res)
    assert s.board["t1"].status == "done"
    assert calls == {"worker": 1, "checker": 1, "prompts": calls["prompts"]}


def test_retry_feeds_back_then_passes(tmp_path):
    s, t, calls = make(tmp_path, [False, True])
    run(t.create_agent(AGENT))
    res = run(t.assign_task(TASK))
    assert "PASSED on attempt 2" in text(res)
    assert "missing file" in calls["prompts"][1]          # feedback reached the worker
    assert s.usage.model_calls == 4


def test_fails_after_max_attempts(tmp_path):
    s, t, _ = make(tmp_path, [False, False, False])
    run(t.create_agent(AGENT))
    res = run(t.assign_task(TASK))
    assert res.get("is_error") and "FAILED after 3" in text(res)
    assert s.board["t1"].status == "failed"


def test_finish_refused_until_done(tmp_path):
    s, t, _ = make(tmp_path, [False, False, False, True])
    run(t.create_agent(AGENT))
    assert run(t.finish({"result": "x"})).get("is_error")              # nothing run yet
    run(t.assign_task(TASK))
    assert "Refused" in text(run(t.finish({"result": "x"})))           # t1 failed
    assert run(t.finish({"result": "x", "give_up": True})).get("is_error")  # budget not out
    run(t.assign_task({**TASK, "task_id": "t1-retry", "replaces": "t1"}))
    assert s.board["t1"].status == "replaced"
    assert not run(t.finish({"result": "done"})).get("is_error")
    assert s.final_result == "done"


def test_budget_stops_assignments(tmp_path):
    s, t, _ = make(tmp_path, [True, True], Budget(max_cost_usd=0.25))
    run(t.create_agent(AGENT))
    run(t.assign_task(TASK))                                           # costs 0.3
    res = run(t.assign_task({**TASK, "task_id": "t2"}))
    assert res.get("is_error") and "Out of budget" in text(res)
    assert not run(t.finish({"result": "partial", "give_up": True})).get("is_error")


def test_board_and_files(tmp_path):
    s, t, _ = make(tmp_path, [True])
    run(t.create_agent(AGENT))
    run(t.assign_task(TASK))
    board = json.loads(text(run(t.view_board({}))))
    assert board["tasks"][0]["status"] == "done"
    assert (tmp_path / "board.json").exists() and (tmp_path / "log.jsonl").exists()


def test_mcp_server_builds(tmp_path):
    _, t, _ = make(tmp_path, [])
    assert t.mcp_server()
