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


# ---- 7.1 dependencies and parallel tasks -------------------------------------------

import time  # noqa: E402


def make_timed(tmp_path, fail=(), delay=0.05, config=None):
    """Worker sleeps `delay`, checker fails the task ids in `fail`. Records (task, start, end)."""
    state = RunState("demo task", config or Config(), tmp_path)
    spans = []

    async def fake_runner(*, prompt, output_schema=None, **kw):
        tid = prompt.split("[", 1)[1].split("]", 1)[0] if "[" in prompt else "?"
        if output_schema:
            ok = tid not in fail
            return AgentResult(text="", structured={"passed": ok, "reason": "r", "short": "s"}, turns=1, cost_usd=0.01)
        start = time.monotonic()
        await asyncio.sleep(delay)
        spans.append((tid, start, time.monotonic()))
        return AgentResult(text="done", turns=1, cost_usd=0.01)

    t = OrchestraTools(state, runner=fake_runner)
    for name in ("a1", "a2", "a3", "a4"):
        run(t.create_agent({**AGENT, "name": name}))
    return state, t, spans


def ptask(tid, agent, **kw):
    return {"agent": agent, "task_id": tid, "title": tid, "task": f"[{tid}] do it", "done_when": "x", **kw}


def overlaps(spans, a, b):
    sa = [s for s in spans if s[0] == a][0]
    sb = [s for s in spans if s[0] == b][0]
    return sa[1] < sb[2] and sb[1] < sa[2]


def test_independent_tasks_overlap_and_dependent_waits(tmp_path):
    s, t, spans = make_timed(tmp_path)
    res = run(t.assign_tasks({"tasks": [
        ptask("r1", "a1"), ptask("r2", "a2"), ptask("r3", "a3"),
        ptask("rep", "a4", depends_on=["r1", "r2", "r3"]),
    ]}))
    assert not res.get("is_error"), text(res)
    assert "4 of 4 tasks passed" in text(res)
    assert overlaps(spans, "r1", "r2") and overlaps(spans, "r2", "r3")
    rep = [x for x in spans if x[0] == "rep"][0]
    assert all(rep[1] >= x[2] for x in spans if x[0] != "rep")   # started after all three ended
    assigned = events(s, "task_assigned")
    assert assigned[3]["depends_on"] == ["r1", "r2", "r3"]


def test_max_parallel_limits_concurrency(tmp_path):
    s, t, spans = make_timed(tmp_path, config=Config(budget=Budget(max_parallel=2)))
    run(t.assign_tasks({"tasks": [ptask("r1", "a1"), ptask("r2", "a2"), ptask("r3", "a3")]}))
    points = sorted([(x[1], 1) for x in spans] + [(x[2], -1) for x in spans])
    level = peak = 0
    for _, d in points:
        level += d
        peak = max(peak, level)
    assert peak == 2


def test_same_agent_tasks_run_one_at_a_time(tmp_path):
    _, t, spans = make_timed(tmp_path)
    run(t.assign_tasks({"tasks": [ptask("r1", "a1"), ptask("r2", "a1")]}))
    assert not overlaps(spans, "r1", "r2")


def test_dependent_of_failed_task_is_not_started(tmp_path):
    s, t, spans = make_timed(tmp_path, fail={"r1"}, config=Config(budget=Budget(max_attempts_per_task=1)))
    res = run(t.assign_tasks({"tasks": [ptask("r1", "a1"), ptask("r2", "a2"), ptask("rep", "a3", depends_on=["r1"])]}))
    assert res.get("is_error") and "1 of 3 tasks passed" in text(res)
    assert "NOT STARTED" in text(res)
    assert s.board["rep"].status == "failed" and s.board["rep"].attempts == 0
    assert "rep" not in [x[0] for x in spans]
    blocked = [e for e in events(s, "task_failed") if e["task_id"] == "rep"][0]
    assert blocked["attempts"] == 0 and "r1" in blocked["reason"]
    # the blocked task can be replaced like any failed one
    assert not run(t.assign_task({**ptask("rep-2", "a3"), "replaces": "rep"})).get("is_error")


def test_two_parallel_tasks_cannot_own_the_same_file(tmp_path):
    s, t, spans = make_timed(tmp_path)
    res = run(t.assign_tasks({"tasks": [ptask("r1", "a1", owns=["report.md"]), ptask("r2", "a2", owns=["report.md"])]}))
    assert res.get("is_error") and "both own" in text(res) and not spans and not s.board
    # fine when one waits for the other
    res = run(t.assign_tasks({"tasks": [ptask("r1", "a1", owns=["report.md"]),
                                        ptask("r2", "a2", owns=["report.md"], depends_on=["r1"])]}))
    assert not res.get("is_error"), text(res)


def test_batch_validation(tmp_path):
    s, t, _ = make_timed(tmp_path)
    loop = run(t.assign_tasks({"tasks": [ptask("x", "a1", depends_on=["y"]), ptask("y", "a2", depends_on=["x"])]}))
    assert loop.get("is_error") and "loop" in text(loop)
    assert "unknown task" in text(run(t.assign_tasks({"tasks": [ptask("x", "a1", depends_on=["nope"])]})))
    assert "unique" in text(run(t.assign_tasks({"tasks": [ptask("x", "a1"), ptask("x", "a2")]})))
    assert "No agent" in text(run(t.assign_tasks({"tasks": [ptask("x", "ghost")]})))
    assert not s.board                                             # nothing registered on refusal


def test_batch_respects_assignment_budget(tmp_path):
    s, t, _ = make_timed(tmp_path, config=Config(budget=Budget(max_assignments=2)))
    res = run(t.assign_tasks({"tasks": [ptask("r1", "a1"), ptask("r2", "a2"), ptask("r3", "a3")]}))
    assert res.get("is_error") and "only 2 assignments left" in text(res)


def test_stop_cancels_every_running_task(tmp_path):
    s, t, spans = make_timed(tmp_path, delay=5)

    async def go():
        job = asyncio.create_task(t.assign_tasks({"tasks": [ptask("r1", "a1"), ptask("r2", "a2")]}))
        await asyncio.sleep(0.1)
        job.cancel()
        try:
            await job
        except asyncio.CancelledError:
            pass
        return [x for x in asyncio.all_tasks() if x.get_name().startswith("task-")]

    assert run(go()) == []                                         # no orphan worker tasks
    assert not spans                                               # nobody finished
    assert not t._owned


def test_owner_released_after_task(tmp_path):
    _, t, _ = make_timed(tmp_path)
    run(t.assign_task(ptask("r1", "a1", owns=["a.md"])))
    assert t._owned == {}


def test_parallel_options_round_trip():
    assert Config.from_options(Config(budget=Budget(max_parallel=5)).to_options()).budget.max_parallel == 5
    assert Config.from_options({"max_parallel": 0}).budget.max_parallel == 1


# ---- 7.4 usage per agent, task and model ----------------------------------------------

def test_usage_events_say_who_spent_it(tmp_path):
    s, t, _ = make(tmp_path, [False, True])
    run(t.create_agent({**AGENT, "tier": "haiku"}))
    run(t.assign_task(TASK))
    u = events(s, "usage")
    assert [(e["agent"], e["role"], e["model"]) for e in u] == [
        ("writer", "worker", "haiku"), ("checker", "checker", "haiku"),
        ("writer", "worker", "sonnet"), ("checker", "checker", "haiku")]
    assert all(e["task_id"] == "t1" for e in u)


def test_usage_breakdown_adds_up(tmp_path):
    from server.summary import fold
    s, t, _ = make(tmp_path, [False, True, True])
    run(t.create_agent({**AGENT, "tier": "haiku"}))
    run(t.create_agent({**AGENT, "name": "coder", "tier": "sonnet"}))
    run(t.assign_task(TASK))
    run(t.assign_task({**TASK, "agent": "coder", "task_id": "t2"}))
    d = fold(s.run_dir)
    by_agent, by_model = d["usage"]["by_agent"], d["usage"]["by_model"]
    assert round(sum(a["cost_usd"] for a in by_agent.values()), 4) == round(d["cost_usd"], 4)
    assert round(sum(m["cost_usd"] for m in by_model.values()), 4) == round(d["cost_usd"], 4)
    assert by_agent["writer"]["models"] == ["haiku", "sonnet"] and by_agent["writer"]["calls"] == 2
    assert by_agent["checker"]["calls"] == 3 and by_agent["coder"]["tasks"] == ["t2"]
    assert by_model["sonnet"]["calls"] == 2                     # writer's step-up + coder


def test_old_usage_events_still_fold(tmp_path):
    from server.summary import fold
    s = RunState("x", Config(), tmp_path)
    s.log("usage", cost_usd=0.5, delta_usd=0.5, model_calls=1, turns=1, assignments=0)
    assert fold(s.run_dir)["usage"]["by_agent"]["unknown"]["cost_usd"] == 0.5
