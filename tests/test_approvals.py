import asyncio
import json

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from orchestra.approvals import ApprovalBroker, make_can_use_tool, preview
from orchestra.catalog import Toolset
from orchestra.config import Config
from orchestra.state import RunState


def toolset():
    return Toolset(gated_servers={"gmail": ["send*"]})


def events(state):
    return [json.loads(l) for l in (state.run_dir / "log.jsonl").read_text().splitlines()]


def test_non_outward_passes_without_asking(tmp_path):
    state = RunState("t", Config(), tmp_path)
    cb = make_can_use_tool(ApprovalBroker(state, interactive=True), toolset(), "editor", "t1")
    res = asyncio.run(cb("mcp__gmail__search_threads", {"q": "x"}, None))
    assert isinstance(res, PermissionResultAllow)
    assert not (tmp_path / "log.jsonl").exists() or not events(state)


def test_cli_mode_denies_outward(tmp_path):
    state = RunState("t", Config(), tmp_path)
    cb = make_can_use_tool(ApprovalBroker(state, interactive=False), toolset(), "editor", "t1")
    res = asyncio.run(cb("mcp__gmail__send_message", {"to": "a"}, None))
    assert isinstance(res, PermissionResultDeny) and "web app" in res.message


def _ask_and_answer(tmp_path, answer):
    state = RunState("t", Config(), tmp_path)
    broker = ApprovalBroker(state, interactive=True)
    cb = make_can_use_tool(broker, toolset(), "editor", "t1")

    async def go():
        task = asyncio.create_task(cb("mcp__gmail__send_message", {"to": "me", "token": "x"}, None))
        await asyncio.sleep(0.01)
        (aid,) = broker.pending
        if answer == "expire":
            broker.expire_all()
        else:
            assert broker.resolve(aid, answer == "approve")
            assert not broker.resolve(aid, True)    # second answer is ignored
        return await task

    return state, asyncio.run(go())


def test_approve(tmp_path):
    state, res = _ask_and_answer(tmp_path, "approve")
    assert isinstance(res, PermissionResultAllow)
    ev = events(state)
    req = next(e for e in ev if e["type"] == "approval_requested")
    assert req["catalog_id"] == "gmail" and "•••" in req["preview"] and '"x"' not in req["preview"]
    assert ev[-1]["type"] == "approval_resolved" and ev[-1]["decision"] == "approved"


def test_deny(tmp_path):
    state, res = _ask_and_answer(tmp_path, "deny")
    assert isinstance(res, PermissionResultDeny) and "Denied" in res.message
    assert events(state)[-1]["decision"] == "denied"


def test_expire(tmp_path):
    state, res = _ask_and_answer(tmp_path, "expire")
    assert isinstance(res, PermissionResultDeny)
    assert events(state)[-1]["decision"] == "expired"


def test_preview_truncates():
    assert len(preview({"body": "x" * 5000})) <= 601
