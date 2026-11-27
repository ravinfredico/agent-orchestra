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


# ---- 7.3 cheap checks first ------------------------------------------------------

from orchestra import checks  # noqa: E402


async def write_report(cwd, **kw):
    (cwd / "report.md").write_text("# Report\n\n## Sources\none two three four five")


def test_checks_validate():
    assert checks.validate([{"type": "file_exists", "path": "a"}], False) is None
    assert "needs" in checks.validate([{"type": "contains", "path": "a"}], False)
    assert "Unknown" in checks.validate([{"type": "rm -rf"}], False)
    assert "shell" in checks.validate([{"type": "command", "run": "pytest -q"}], False)
    assert checks.validate([{"type": "command", "run": "pytest -q"}], True) is None


def test_check_kinds(tmp_path):
    (tmp_path / "r").mkdir()
    for i in range(3):
        (tmp_path / "r" / f"{i}.md").write_text("x")
    (tmp_path / "a.md").write_text("Hello World " * 10)
    ok, res = run(checks.run_checks([
        {"type": "file_exists", "path": "a.md"},
        {"type": "file_count", "glob": "r/*.md", "min": 3},
        {"type": "contains", "path": "a.md", "text": "hello world"},
        {"type": "min_words", "path": "a.md", "min": 20},
        {"type": "command", "run": "python -c \"import sys; sys.exit(0)\""},
    ], tmp_path))
    assert ok, res
    ok, res = run(checks.run_checks([
        {"type": "file_exists", "path": "../outside.md"},
        {"type": "file_count", "glob": "r/*.md", "min": 4},
        {"type": "min_words", "path": "a.md", "min": 21},
        {"type": "command", "run": "python -c \"import sys; sys.exit(3)\""},
        {"type": "contains", "path": "nope.md", "text": "x"},
    ], tmp_path))
    assert not ok and not any(r["passed"] for r in res)
    assert res[0]["detail"] == "path leaves the workspace" and res[3]["detail"].startswith("exit 3")


def test_failing_check_skips_model_checker(tmp_path):
    attempts = {"n": 0}                               # 2nd attempt: worker writes the file, checker passes

    async def worker(cwd, **kw):
        attempts["n"] += 1
        if attempts["n"] == 2:
            await write_report(cwd)
    s2, t2, calls2 = make(tmp_path, [True], worker=worker)
    run(t2.create_agent(AGENT))
    res = run(t2.assign_task({**TASK, "checks": [{"type": "file_exists", "path": "report.md"}]}))
    assert "PASSED on attempt 2" in text(res)
    assert [c["checker"] for c in calls2] == [False, False, True]   # no checker after attempt 1
    failed = events(s2, "attempt_failed")[0]
    assert failed["checked_by"] == "checks" and "no model was asked" in failed["reason"]
    assert failed["checks"][0]["passed"] is False
    assert events(s2, "task_assigned")[0]["checks"] == ["report.md exists"]
    assert "Already verified by commands" in calls2[-1]["prompt"]


def test_checks_only_skips_model_checker(tmp_path):
    s, t, calls = make(tmp_path, [], worker=write_report)
    run(t.create_agent(AGENT))
    res = run(t.assign_task({**TASK, "checks_only": True, "checks": [
        {"type": "file_exists", "path": "report.md"}, {"type": "contains", "path": "report.md", "text": "## Sources"}]}))
    assert "PASSED on attempt 1" in text(res)
    assert not any(c["checker"] for c in calls)
    assert events(s, "task_passed")[0]["checked_by"] == "checks"
    assert s.usage.model_calls == 1                 # the worker only


def test_command_check_refused_without_shell(tmp_path):
    _, t, calls = make(tmp_path)
    run(t.create_agent(AGENT))
    res = run(t.assign_task({**TASK, "checks": [{"type": "command", "run": "pytest -q"}]}))
    assert res.get("is_error") and "shell" in text(res) and not calls


def test_checks_only_needs_checks(tmp_path):
    _, t, _ = make(tmp_path)
    run(t.create_agent(AGENT))
    assert run(t.assign_task({**TASK, "checks_only": True})).get("is_error")


def test_summary_folds_tier_and_checks(tmp_path):
    from server.summary import fold
    s, t, _ = make(tmp_path, [False, True], worker=write_report)
    run(t.create_agent({**AGENT, "tier": "haiku", "tier_reason": "simple"}))
    run(t.assign_task({**TASK, "checks": [{"type": "file_exists", "path": "report.md"}]}))
    b = fold(s.run_dir)["board"][0]
    assert (b["tier"], b["tier_reason"], b["checks"]) == ("sonnet", "simple", ["report.md exists"])
    assert [h["tier"] for h in b["history"]] == ["haiku", "sonnet"]
    assert b["history"][0]["checks"][0]["passed"] and b["history"][0]["checked_by"] == "model"
