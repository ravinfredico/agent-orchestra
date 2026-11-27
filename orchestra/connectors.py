"""Your claude.ai connectors (Figma, Gmail, Notion, Slack, ...) as catalog entries.

Claude Code sessions signed in with a claude.ai account, Agent SDK runs included, load the connectors
you added at claude.ai automatically. Their tools are named `mcp__claude_ai_<Name>__<tool>`.
This module finds them with `claude mcp list` (a health check, no model call, no usage) so the
orchestrator can give them to agents like any other catalog tool.

Safety (see catalog.Toolset):
- An agent only gets the connectors it was given. The others are hidden (`disallowed_tools`), and
  agents with none run with ENABLE_CLAUDEAI_MCP_SERVERS=false.
- Reading tools (get, list, search, read, ...) run freely. Anything else asks you first.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass

PREFIX = "claude.ai "
# Tool names that only read. Everything else on a connector is treated as outward and needs approval.
READ_PATTERNS = ["get*", "list*", "search*", "read*", "fetch*", "find*", "query*", "view*", "describe*",
                 "lookup*", "whoami*", "download*", "export*", "*_get", "*_list", "*_search", "*_read",
                 "*_info", "*_details", "*_metadata", "*screenshot*", "*context*"]
DISABLE_ENV = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
_LINE = re.compile(r"^(?P<name>[^:\n]+?):\s*(?P<url>\S*)\s*\((?P<type>[A-Za-z]+)\)\s*-\s*(?P<status>.+)$")
_CACHE: dict = {"t": 0.0, "items": None}
CACHE_SECONDS = 300


@dataclass
class Connector:
    name: str           # as Claude Code shows it, e.g. "claude.ai Figma"
    url: str
    status: str         # connected | needs_auth | failed | unknown

    @property
    def label(self) -> str:
        return self.name[len(PREFIX):] if self.name.startswith(PREFIX) else self.name

    @property
    def id(self) -> str:
        """Catalog id, e.g. connector.figma."""
        return "connector." + re.sub(r"[^a-z0-9]+", "-", self.label.lower()).strip("-")

    @property
    def server(self) -> str:
        """The MCP server name inside tool names: 'claude.ai Figma' -> 'claude_ai_Figma'."""
        return server_key(self.name)


def server_key(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _status(text: str) -> str:
    t = text.lower()
    if "connected" in t and "fail" not in t and "not" not in t:
        return "connected"
    if "auth" in t:
        return "needs_auth"
    if "fail" in t or "error" in t:
        return "failed"
    return "unknown"


def parse_mcp_list(text: str) -> list[Connector]:
    """Parse `claude mcp list`. Keeps claude.ai connectors only (your own servers come from the catalog)."""
    out = []
    for line in (text or "").splitlines():
        m = _LINE.match(line.strip())
        if m and m.group("name").startswith(PREFIX):
            out.append(Connector(m.group("name").strip(), m.group("url"), _status(m.group("status"))))
    return out


def discover(run=None, timeout: float = 30.0, use_cache: bool = True) -> list[Connector]:
    """Your claude.ai connectors, cached for 5 minutes. Empty if Claude Code is missing or signed out."""
    if use_cache and _CACHE["items"] is not None and time.time() - _CACHE["t"] < CACHE_SECONDS:
        return _CACHE["items"]
    items: list[Connector] = []
    try:
        if run is None:
            exe = shutil.which("claude")
            if not exe:
                return []
            res = subprocess.run([exe, "mcp", "list"], capture_output=True, text=True, timeout=timeout)
            text = res.stdout
        else:
            text = run()
        items = parse_mcp_list(text)
    except (OSError, subprocess.SubprocessError):
        items = []
    _CACHE.update(t=time.time(), items=items)
    return items


def description(c: Connector) -> str:
    return f"Your claude.ai {c.label} connector. Reading is free; anything that sends, creates or changes needs your approval"


def unavailable(c: Connector) -> str | None:
    if c.status == "connected":
        return None
    if c.status == "needs_auth":
        return f"sign in to {c.label} once: run claude, then /mcp (or reconnect it at claude.ai, Settings, Connectors)"
    return f"{c.label} is not reachable right now ({c.status})"
