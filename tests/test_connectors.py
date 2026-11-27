"""claude.ai connectors as catalog tools: discovery, who may use them, approvals. Offline."""

import asyncio

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from orchestra import connectors
from orchestra.approvals import make_can_use_tool
from orchestra.catalog import load_catalog, with_connectors
from orchestra.config import Config

MCP_LIST = """Checking MCP server health…

claude.ai Figma: https://mcp.figma.com/mcp (HTTP) - ✓ Connected
claude.ai Gmail: https://gmail.mcp.claude.com/mcp (HTTP) - ✓ Connected
claude.ai Notion: https://mcp.notion.com/mcp (HTTP) - ! Needs authentication
claude.ai Asana: https://mcp.asana.com/sse (SSE) - ✗ Failed to connect
my-local: npx my-server (stdio) - ✓ Connected
"""


def found():
    return connectors.parse_mcp_list(MCP_LIST)


def test_parse_keeps_claude_ai_connectors_with_status():
    cs = found()
    assert [(c.label, c.status) for c in cs] == [("Figma", "connected"), ("Gmail", "connected"),
                                                 ("Notion", "needs_auth"), ("Asana", "failed")]
    assert cs[0].id == "connector.figma" and cs[0].server == "claude_ai_Figma"


def test_discover_caches_and_survives_a_missing_cli():
    calls = []
    def run():
        calls.append(1)
        return MCP_LIST
    assert len(connectors.discover(run=run, use_cache=False)) == 4
    assert len(connectors.discover(run=run)) == 4 and len(calls) == 1          # cached
    def boom():
        raise OSError("claude not found")
    assert connectors.discover(run=boom, use_cache=False) == []


def test_catalog_entries_and_availability():
    cat = with_connectors(load_catalog(), found())
    fig, notion = cat.by_id["connector.figma"], cat.by_id["connector.notion"]
    assert fig.kind == "connector" and fig.unavailable is None and fig.public()["label"] == "Figma"
    assert "sign in to Notion" in notion.unavailable
    ids = cat.available_ids(Config())
    assert "connector.figma" in ids and "connector.notion" not in ids and "connector.asana" not in ids


def test_an_agent_sees_only_its_own_connectors():
    cat = with_connectors(load_catalog(), found())
    ts = cat.toolset(["files.read", "connector.figma"], Config())
    assert ts.needs_approval_callback and not ts.env                          # connectors stay loaded
    assert "mcp__claude_ai_Gmail" in ts.disallowed_tools and "mcp__claude_ai_Figma" not in ts.disallowed_tools
    assert ts.owns("mcp__claude_ai_Figma__get_screenshot") and ts.owns("Read")
    assert not ts.owns("mcp__claude_ai_Gmail__send_message") and not ts.owns("Bash")
    assert not ts.is_outward("mcp__claude_ai_Figma__get_design_context")
    assert not ts.is_outward("mcp__claude_ai_Figma__search_design_system")
    assert ts.is_outward("mcp__claude_ai_Figma__use_figma")                  # writes to your file: ask
    assert ts.is_outward("mcp__claude_ai_Figma__create_new_file")
    assert ts.catalog_id_for("mcp__claude_ai_Figma__use_figma") == "connector.figma"

    plain = cat.toolset(["files.read"], Config())
    assert plain.env == {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}             # none loaded at all


class Broker:
    interactive = True

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    async def request(self, **kw):
        self.asked.append(kw)
        return self.answer


def decide(ts, broker, tool):
    return asyncio.run(make_can_use_tool(broker, ts, "designer", "t1")(tool, {"x": 1}, None))


def test_approvals_for_connector_tools():
    ts = with_connectors(load_catalog(), found()).toolset(["connector.figma"], Config())
    b = Broker(True)
    assert isinstance(decide(ts, b, "mcp__claude_ai_Figma__get_screenshot"), PermissionResultAllow) and not b.asked
    assert isinstance(decide(ts, b, "mcp__claude_ai_Figma__use_figma"), PermissionResultAllow)
    assert b.asked[0]["catalog_id"] == "connector.figma"
    assert isinstance(decide(ts, Broker(False), "mcp__claude_ai_Figma__use_figma"), PermissionResultDeny)
    denied = decide(ts, b, "mcp__claude_ai_Gmail__send_message")             # not given: never asked
    assert isinstance(denied, PermissionResultDeny) and len(b.asked) == 1


def test_demo_mode_lists_connectors(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.runs import RunManager
    monkeypatch.delenv("APP_TOKEN", raising=False)
    mgr = RunManager(tmp_path / "runs", fake_mode=True, fake_delay=0.0)
    with TestClient(create_app(mgr, web_dist=tmp_path / "x", schedule=False)) as c:
        cat = {e["id"]: e for e in c.get("/api/catalog").json()}
        assert cat["connector.figma"]["label"] == "Figma" and cat["connector.figma"]["unavailable"] is None
        assert cat["connector.slack"]["unavailable"]
        r = c.post("/api/teams", json={"name": "Marketing", "members": [
            {"name": "designer", "role": "Makes social graphics", "tools": ["connector.figma", "files.write"], "tier": "sonnet"}]})
        assert r.status_code == 201, r.text


def test_real_mode_adds_discovered_connectors(tmp_path):
    from server.runs import RunManager
    mgr = RunManager(tmp_path / "runs", fake_mode=False)
    mgr.discover = found
    assert "connector.figma" in mgr.catalog.by_id
