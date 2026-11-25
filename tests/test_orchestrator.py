"""Outer loop tests with a scripted orchestrator client. No model calls."""

import asyncio
import json

from orchestra.config import Budget, Config
from orchestra.fake import (FakeRunner, FakeTask, demo_catalog, demo_runner, demo_script,
                            fake_client_factory, DEMO_TASK)
from orchestra.orchestrator import (classify_error, continue_task, create_run, execute_run,
                                    follow_up_task)
from orchestra.state import read_events


def types(state):
    return [e["type"] for e in read_events(state.run_dir)]


def go(state, script, runner, **kw):
    factory = fake_client_factory(script, {"state": state})
    return asyncio.run(execute_run(state, runner=runner, client_factory=factory, **kw))


def test_create_run_returns_immediately_with_run_started(tmp_path):
    s = create_run("do it", Config(), tmp_path)
    assert s.status == "running" and types(s) == ["run_started"]
    meta = json.loads((s.run_dir / "meta.json").read_text())
    assert meta["task"] == "do it" and meta["auth_mode"] in ("plan", "api_key")


def test_demo_scenario_end_to_end(tmp_path):
    s = create_run(DEMO_TASK, Config(), tmp_path)

    async def answer_approvals(e):
        pass

    def auto_approve(event):
        if event["type"] == "approval_requested":
            asyncio.get_event_loop().call_soon(s.approvals.resolve, event["approval_id"], True)

    s.add_listener(auto_approve)
    go(s, demo_script, demo_runner(delay=0), catalog=demo_catalog(), interactive=True)
    t = types(s)
    assert s.status == "finished"
    assert t.count("agent_created") == 4
    assert "task_replaced" in t and "approval_requested" in t and t[-1] == "finished"
    board = json.loads((s.run_dir / "board.json").read_text())["board"]
    assert board["report-1"]["status"] == "replaced" and board["report-2"]["status"] == "done"
    assert (s.workspace / "report.md").exists()
    assert (s.run_dir / "final.md").read_text().startswith("Wrote report.md")


def test_cancel_logs_run_stopped(tmp_path):
    s = create_run("slow", Config(), tmp_path)

    async def script(tools):
        await tools.create_agent({"name": "a", "role": "r", "system_prompt": "p", "tools": ["files.read"]})
        await tools.assign_task({"agent": "a", "task_id": "t1", "title": "Slow", "task": "[slow]", "done_when": "x"})
        yield "never"

    runner = FakeRunner({"[slow]": FakeTask(tools=[("Read", {})] * 50)}, delay=0.05)

    async def main():
        task = asyncio.create_task(execute_run(s, runner=runner, client_factory=fake_client_factory(script, {"state": s})))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(main())
    assert s.status == "stopped" and types(s)[-1] == "run_stopped"
    assert (s.run_dir / "board.json").exists()


def test_crash_is_classified(tmp_path):
    s = create_run("x", Config(), tmp_path)

    class Boom:
        def __init__(self, options): pass
        async def __aenter__(self): raise RuntimeError("Claude Code: not logged in")
        async def __aexit__(self, *a): return False

    asyncio.run(execute_run(s, runner=FakeRunner({}), client_factory=Boom))
    last = read_events(s.run_dir)[-1]
    assert last["type"] == "run_failed" and last["kind"] == "auth" and "/login" in last["hint"]
    assert s.status == "failed"


def test_classify_error():
    assert classify_error("429 rate limit")[0] == "limit"
    assert classify_error("weird")[0] == "crash"


def test_no_finish_ends_as_give_up(tmp_path):
    s = create_run("x", Config(budget=Budget(max_nudges=1)), tmp_path)

    async def script(tools):
        yield "thinking"

    go(s, script, FakeRunner({}))
    assert types(s).count("nudge") == 2 and s.status == "gave_up"


def test_continue_and_follow_up_prompts(tmp_path):
    parent = create_run(DEMO_TASK, Config(), tmp_path)

    async def script(tools):
        await tools.create_agent({"name": "a", "role": "r", "system_prompt": "p", "tools": ["files.write"]})
        await tools.assign_task({"agent": "a", "task_id": "t1", "title": "Draft", "task": "[draft] write draft.md",
                                 "done_when": "draft.md exists"})
        yield "stopping"

    go(parent, script, FakeRunner({"[draft]": FakeTask(verdicts=[False], files=[("draft.md", "x")])}))
    text = continue_task(parent.run_dir)
    assert "Unfinished" in text and "Draft" in text and DEMO_TASK in text
    child = create_run(text, Config(), tmp_path, parent_id=parent.run_id, seed_from=parent.workspace)
    assert (child.workspace / "draft.md").exists() and not (child.workspace / ".agents").exists()
    assert child.parent_id == parent.run_id
    assert "translate it" in follow_up_task(parent.run_dir, "translate it")


def test_build_demo_produces_a_working_app(tmp_path):
    import subprocess
    import sys

    from orchestra.fake import DEMO_BUILD_TASK, demo_build_runner, demo_build_script

    s = create_run(DEMO_BUILD_TASK, Config(allow_bash=True), tmp_path)
    go(s, demo_build_script, demo_build_runner(delay=0), catalog=demo_catalog(), interactive=True)
    t = types(s)
    assert s.status == "finished" and t[-1] == "finished"
    board = json.loads((s.run_dir / "board.json").read_text())["board"]
    assert board["app-1"]["attempts"] == 2 and board["app-1"]["status"] == "done"
    assert board["tests-1"]["status"] == "replaced" and board["app-fix"]["status"] == "done"
    assert {"todo.py", "test_todo.py", "README.md"} <= {p.name for p in s.workspace.iterdir()}
    # the demo app is real: its own test suite passes
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=s.workspace,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "11 passed" in r.stdout


def test_pick_demo_matches_the_task():
    from orchestra.fake import demo_build_script, pick_demo
    assert pick_demo("Build a Python CLI todo app with pytest tests")[1] is demo_build_script
    assert pick_demo("Research the top 5 Indonesian e-wallets")[1] is demo_script
