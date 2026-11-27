"""M7 (parallel and cheaper): model tiers, cheap checks, options, parallel tasks, usage breakdown.

Offline: the runner is faked, no model calls.
"""

import asyncio
import json

from orchestra.config import Budget, Config, clamp_tier, step_up
from orchestra.runner import AgentResult
from orchestra.state import RunState
from orchestra.tools import OrchestraTools


def run(coro):
    return asyncio.run(coro)


def text(res):
    return res["content"][0]["text"]


def events(state, kind=None):
    out = [json.loads(line) for line in (state.run_dir / "log.jsonl").read_text().splitlines()]
    return [e for e in out if kind is None or e["type"] == kind]


def make(tmp_path, verdicts=(), config=None, worker=None):
    """verdicts: bools the fake checker returns in order. Records every runner call."""
    state = RunState("demo task", config or Config(), tmp_path)
    calls = []
    it = iter(verdicts)

    async def fake_runner(*, prompt, output_schema=None, **kw):
        calls.append({"prompt": prompt, "checker": bool(output_schema), **kw})
        if output_schema:
            ok = next(it)
            return AgentResult(text="", structured={"passed": ok, "reason": "ok" if ok else "bad", "short": "x"},
                               turns=1, cost_usd=0.01)
        if worker:
            await worker(prompt=prompt, **kw)
        return AgentResult(text="done", turns=2, cost_usd=0.1)

    return state, OrchestraTools(state, runner=fake_runner), calls


AGENT = {"name": "writer", "role": "writes", "system_prompt": "You write.", "tools": ["files.read", "files.write"]}
TASK = {"agent": "writer", "task_id": "t1", "title": "Write report", "task": "write report.md",
        "done_when": "report.md exists"}


# ---- 7.2 model tier per task ---------------------------------------------------

def test_tier_helpers():
    assert step_up("haiku", "opus") == "sonnet"
    assert step_up("sonnet", "opus") == "opus"
    assert step_up("sonnet", "sonnet") is None
    assert step_up("opus", "opus") is None
    assert clamp_tier("opus", "sonnet") == "sonnet"


def test_agent_tier_passed_to_runner(tmp_path):
    s, t, calls = make(tmp_path, [True])
    run(t.create_agent({**AGENT, "tier": "haiku", "tier_reason": "simple summary"}))
    run(t.assign_task(TASK))
    worker = [c for c in calls if not c["checker"]]
    assert worker[0]["model"] == "haiku"
    created = events(s, "agent_created")[0]
    assert created["model"] == "haiku" and created["tier_reason"] == "simple summary"
    assigned = events(s, "task_assigned")[0]
    assert assigned["tier"] == "haiku" and assigned["tier_reason"] == "simple summary"


def test_task_tier_overrides_agent(tmp_path):
    s, t, calls = make(tmp_path, [True])
    run(t.create_agent({**AGENT, "tier": "haiku"}))
    run(t.assign_task({**TASK, "tier": "sonnet", "tier_reason": "needs code"}))
    assert [c for c in calls if not c["checker"]][0]["model"] == "sonnet"
    assert events(s, "task_assigned")[0]["tier_reason"] == "needs code"


def test_unknown_tier_rejected(tmp_path):
    _, t, _ = make(tmp_path)
    res = run(t.create_agent({**AGENT, "tier": "gpt"}))
    assert res.get("is_error") and "tier" in text(res)


def test_step_up_once_on_failure(tmp_path):
    s, t, calls = make(tmp_path, [False, False, True])
    run(t.create_agent({**AGENT, "tier": "haiku"}))
    run(t.assign_task(TASK))
    models = [c["model"] for c in calls if not c["checker"]]
    assert models == ["haiku", "sonnet", "sonnet"]         # one step up, once
    assert [e["tier"] for e in events(s, "attempt_started")] == ["haiku", "sonnet", "sonnet"]


def test_step_up_respects_max_tier(tmp_path):
    _, t, calls = make(tmp_path, [False, True], Config(max_tier="sonnet"))
    run(t.create_agent({**AGENT, "tier": "opus"}))          # clamped to sonnet
    run(t.assign_task(TASK))
    assert [c["model"] for c in calls if not c["checker"]] == ["sonnet", "sonnet"]


def test_sonnet_steps_up_to_opus_by_default(tmp_path):
    _, t, calls = make(tmp_path, [False, True])
    run(t.create_agent({**AGENT, "tier": "sonnet"}))
    run(t.assign_task(TASK))
    assert [c["model"] for c in calls if not c["checker"]] == ["sonnet", "opus"]


def test_run_override_ignores_orchestrator_pick(tmp_path):
    s, t, calls = make(tmp_path, [True], Config(pick_tier=False, worker_model="haiku"))
    run(t.create_agent({**AGENT, "tier": "opus"}))
    run(t.assign_task({**TASK, "tier": "opus"}))
    assert [c["model"] for c in calls if not c["checker"]] == ["haiku"]
    assert events(s, "task_assigned")[0]["tier_reason"] == "set by the run"


def test_options_round_trip():
    o = Config(pick_tier=False, max_tier="sonnet", budget=Budget(max_worker_turns=12)).to_options()
    c = Config.from_options(o)
    assert (c.pick_tier, c.max_tier, c.budget.max_worker_turns) == (False, "sonnet", 12)
    assert Config.from_options({"max_tier": "bogus"}).max_tier == "opus"
