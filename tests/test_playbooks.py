import asyncio
import json

import pytest

from orchestra import prompts
from orchestra.config import Budget, Config
from orchestra.playbooks import _parse, load_playbooks, summary_lines
from orchestra.state import RunState, read_events
from orchestra.tools import OrchestraTools


def test_all_playbooks_load_with_front_matter():
    books = load_playbooks()
    assert {"research-report", "build-with-tests", "repo-change", "writing", "general"} <= set(books)
    for b in books.values():
        assert b.title and b.when and "## Steps" in b.body and "## Pitfalls" in b.body


def test_bad_front_matter_is_rejected(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\nid: x\n---\nbody")
    with pytest.raises(ValueError, match="title"):
        _parse(p)


def test_read_playbook_logs_event_and_rejects_unknown(tmp_path):
    state = RunState("t", Config(), tmp_path)
    tools = OrchestraTools(state)
    res = asyncio.run(tools.read_playbook({"id": "research-report"}))
    assert not res.get("is_error") and "Pitfalls" in res["content"][0]["text"]
    ev = read_events(state.run_dir)[-1]
    assert ev["type"] == "playbook_chosen" and ev["title"] == "Research report"
    bad = asyncio.run(tools.read_playbook({"id": "nope"}))
    assert bad.get("is_error") and "general" in bad["content"][0]["text"]


def test_prompt_lists_playbooks_and_forced_choice():
    books = load_playbooks()
    auto = prompts.orchestrator_prompt("- web: x", Budget(), summary_lines(books))
    for b in books.values():
        assert b.id in auto
    assert "call read_playbook with the id that fits" in auto
    forced = prompts.orchestrator_prompt("- web: x", Budget(), summary_lines(books), "writing")
    assert 'read_playbook("writing")' in forced


def test_playbook_option_roundtrip():
    assert Config.from_options({"playbook": "writing"}).to_options()["playbook"] == "writing"
    assert Config.from_options({}).playbook == "auto"
