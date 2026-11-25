import json

from orchestra.catalog import load_catalog
from orchestra.config import Config


def write(tmp_path, entries):
    p = tmp_path / "cat.json"
    p.write_text(json.dumps(entries))
    return p


ENTRIES = [
    {"id": "files.read", "kind": "builtin", "tools": ["Read", "Glob"], "risk": "read", "description": "read"},
    {"id": "shell", "kind": "builtin", "tools": ["Bash"], "risk": "shell", "requires": "allow_bash", "description": "sh"},
    {"id": "browser", "kind": "mcp", "risk": "read", "description": "browser",
     "server": {"type": "stdio", "command": "npx", "args": ["@playwright/mcp"]}},
    {"id": "gmail", "kind": "mcp", "risk": "outward", "description": "mail", "outward_tools": ["send*"],
     "server": {"type": "http", "url": "${TEST_MAIL_URL}", "headers": {"Authorization": "Bearer ${TEST_MAIL_TOKEN}"}}},
    {"id": "off", "kind": "builtin", "tools": ["Read"], "risk": "read", "description": "x", "enabled": False},
]


def test_repo_catalog_loads():
    cat = load_catalog()
    ids = cat.available_ids(Config())
    assert {"files.read", "files.write", "web", "browser"} <= set(ids)
    assert "shell" not in ids and "shell" in cat.available_ids(Config(allow_bash=True))


def test_missing_env_makes_entry_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_MAIL_URL", raising=False)
    cat = load_catalog(write(tmp_path, ENTRIES), plugins_dir=tmp_path / "none")
    assert "gmail" not in cat.available_ids(Config())
    assert "TEST_MAIL_URL" in cat.by_id["gmail"].unavailable
    assert "off" not in cat.available_ids(Config())


def test_toolset_mapping_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_MAIL_URL", "https://mail.example")
    monkeypatch.setenv("TEST_MAIL_TOKEN", "s3cret")
    cat = load_catalog(write(tmp_path, ENTRIES), plugins_dir=tmp_path / "none")
    ts = cat.toolset(["files.read", "browser", "gmail"], Config())
    assert ts.tools == ["Read", "Glob"]
    assert "mcp__browser" in ts.allowed_tools and "mcp__gmail" not in ts.allowed_tools
    assert ts.mcp_servers["gmail"]["url"] == "https://mail.example"
    assert ts.mcp_servers["gmail"]["headers"]["Authorization"] == "Bearer s3cret"
    assert ts.needs_approval_callback
    assert ts.is_outward("mcp__gmail__send_message")
    assert not ts.is_outward("mcp__gmail__search_threads")
    assert not ts.is_outward("mcp__browser__browser_click")
    # secrets never in the public view
    assert "s3cret" not in json.dumps(cat.by_id["gmail"].public())


def test_run_catalog_narrows_non_builtin(tmp_path, monkeypatch):
    cat = load_catalog(write(tmp_path, ENTRIES), plugins_dir=tmp_path / "none")
    ids = cat.available_ids(Config(catalog=["files.read"]))
    assert "browser" not in ids and "files.read" in ids


def test_plugins_discovered(tmp_path):
    plug = tmp_path / "plugins" / "notes"
    (plug / ".claude-plugin").mkdir(parents=True)
    (plug / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "notes", "description": "Take notes"}))
    cat = load_catalog(write(tmp_path, ENTRIES[:1]), plugins_dir=tmp_path / "plugins")
    assert "plugin.notes" in cat.available_ids(Config())
    ts = cat.toolset(["plugin.notes"], Config())
    assert ts.plugins[0]["type"] == "local" and ts.plugins[0]["path"].endswith("notes")


def test_unknown_catalog_tool_rejected_by_create_agent(tmp_path):
    import asyncio
    from orchestra.state import RunState
    from orchestra.tools import OrchestraTools
    state = RunState("t", Config(), tmp_path / "run")
    tools = OrchestraTools(state, catalog=load_catalog(write(tmp_path, ENTRIES), plugins_dir=tmp_path / "none"))
    res = asyncio.run(tools.create_agent({"name": "a", "role": "r", "system_prompt": "p", "tools": ["gmail"]}))
    assert res.get("is_error")   # gmail has no credentials, so it is not offered
