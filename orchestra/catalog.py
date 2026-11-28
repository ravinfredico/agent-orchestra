"""The tool catalog: the only tools the orchestrator can give its agents.

Entries come from `tools.catalog.json` (repo root) plus local Claude Code plugins found in `plugins/`.
Each entry has a risk level. `outward` tools (send, post, book) always go through user approval.

    cat = load_catalog()
    ids = [e.id for e in cat.available(config)]
    toolset = cat.toolset(["files.read", "browser"], config)   # -> SDK options for one agent
"""

import copy
import fnmatch
import json
import os
import sys
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import connectors
from .connectors import DISABLE_ENV, READ_PATTERNS, server_key

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_PATH = ROOT / "tools.catalog.json"
DEFAULT_PLUGINS_DIR = ROOT / "plugins"
RISKS = ("read", "write", "shell", "outward")
_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")

# Used when tools.catalog.json is missing, so the engine always has the basics.
BUILTIN_ENTRIES = [
    {"id": "files.read", "kind": "builtin", "tools": ["Read", "Glob", "Grep"], "risk": "read",
     "description": "Read and search files in the workspace"},
    {"id": "files.write", "kind": "builtin", "tools": ["Write", "Edit"], "risk": "write",
     "description": "Create and edit files in the workspace"},
    {"id": "web", "kind": "builtin", "tools": ["WebSearch", "WebFetch"], "risk": "read",
     "description": "Search the web and read pages"},
    {"id": "shell", "kind": "builtin", "tools": ["Bash"], "risk": "shell", "requires": "allow_bash",
     "description": "Run commands in the sandbox (code, tests, installs)"},
]


@dataclass
class Entry:
    id: str
    kind: str                         # builtin | mcp | plugin | connector
    description: str
    risk: str = "read"
    tools: list[str] = field(default_factory=list)       # builtin tool names
    server: dict | None = None                           # mcp server config
    path: str | None = None                              # plugin folder
    outward_tools: list[str] = field(default_factory=list)  # glob patterns of outward tool names
    enabled: bool = True
    requires: str | None = None       # e.g. "allow_bash"
    unavailable: str | None = None    # why it can't be used right now (missing env var, etc.)
    connector: str | None = None      # claude.ai connector name, e.g. "claude.ai Figma" (kind connector)

    def public(self) -> dict:
        """Safe to send to the browser: no server config, no secrets."""
        return {"id": self.id, "kind": self.kind, "description": self.description, "risk": self.risk,
                "enabled": self.enabled, "requires": self.requires, "unavailable": self.unavailable,
                "label": self.connector[len(connectors.PREFIX):] if self.connector else None}


@dataclass
class Toolset:
    """SDK options for one agent, built from catalog ids."""
    tools: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict = field(default_factory=dict)
    plugins: list[dict] = field(default_factory=list)
    gated_servers: dict[str, list[str]] = field(default_factory=dict)  # server -> outward patterns
    read_only_servers: dict[str, list[str]] = field(default_factory=dict)  # server -> read patterns; the rest is outward
    server_ids: dict[str, str] = field(default_factory=dict)          # server name -> catalog id
    env: dict[str, str] = field(default_factory=dict)                 # extra env for the agent's session
    disallowed_tools: list[str] = field(default_factory=list)         # hidden from the agent entirely

    @property
    def needs_approval_callback(self) -> bool:
        return bool(self.gated_servers or self.read_only_servers)

    def is_outward(self, tool_name: str) -> bool:
        """tool_name like 'mcp__gmail__send_message'."""
        m = re.match(r"mcp__(.+?)__(.+)", tool_name)
        if not m:
            return False
        server, name = m.group(1), m.group(2)
        if server in self.read_only_servers:
            return not any(fnmatch.fnmatch(name.lower(), p) for p in self.read_only_servers[server])
        if server not in self.gated_servers:
            return False
        return any(fnmatch.fnmatch(name, p) for p in self.gated_servers[server])

    def owns(self, tool_name: str) -> bool:
        """Was this tool given to the agent? Claude Code can load tools we never chose (connectors)."""
        m = re.match(r"mcp__(.+?)__", tool_name)
        if not m:
            return tool_name in self.tools
        s = m.group(1)
        return s in self.mcp_servers or s in self.read_only_servers or s in self.gated_servers \
            or f"mcp__{s}" in self.allowed_tools

    def catalog_id_for(self, tool_name: str) -> str:
        m = re.match(r"mcp__(.+?)__", tool_name)
        return self.server_ids.get(m.group(1), m.group(1)) if m else tool_name


# Filled in by the app, not .env: lets catalog entries start servers that ship in this repo.
BUILTIN_VARS = {"ORCHESTRA_ROOT": str(Path(__file__).resolve().parent.parent), "PYTHON": sys.executable}


def _substitute(value, missing: set):
    if isinstance(value, str):
        def rep(m):
            v = BUILTIN_VARS.get(m.group(1)) or os.environ.get(m.group(1)) or None
            if v is None:
                missing.add(m.group(1))
                return ""
            return v
        return _VAR.sub(rep, value)
    if isinstance(value, dict):
        return {k: _substitute(v, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, missing) for v in value]
    return value


def connector_entries(found) -> list[Entry]:
    """Catalog entries for discovered claude.ai connectors (orchestra.connectors.discover())."""
    return [Entry(id=c.id, kind="connector", description=connectors.description(c), risk="outward",
                  connector=c.name, unavailable=connectors.unavailable(c)) for c in found]


def with_connectors(catalog: "Catalog", found) -> "Catalog":
    known = {e.id for e in catalog.entries}
    return Catalog(catalog.entries + [e for e in connector_entries(found) if e.id not in known])


def _server_name(entry_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", entry_id)


class Catalog:
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self.by_id = {e.id: e for e in entries}

    def available(self, config) -> list[Entry]:
        """Entries the orchestrator may use in this run."""
        out = []
        allowed = set(config.catalog) if config.catalog and "*" not in config.catalog else None
        for e in self.entries:
            if not e.enabled or e.unavailable:
                continue
            if e.requires == "allow_bash" and not config.allow_bash:
                continue
            if allowed is not None and e.id not in allowed and e.kind != "builtin":
                continue
            out.append(e)
        return out

    def available_ids(self, config) -> list[str]:
        return [e.id for e in self.available(config)]

    def toolset(self, ids: list[str], config) -> Toolset:
        ts = Toolset()
        for i in ids:
            e = self.by_id[i]
            if e.kind == "builtin":
                ts.tools += e.tools
                ts.allowed_tools += e.tools
            elif e.kind == "mcp" and e.server:
                name = _server_name(e.id)
                missing: set = set()
                ts.mcp_servers[name] = _substitute(copy.deepcopy(e.server), missing)
                if e.risk == "outward" or e.outward_tools:
                    # every tool of this server goes through the approval callback, which lets
                    # non-outward ones straight through and asks the user for the rest
                    ts.gated_servers[name] = e.outward_tools or ["*"]
                else:
                    ts.allowed_tools.append(f"mcp__{name}")
            elif e.kind == "plugin" and e.path:
                ts.plugins.append({"type": "local", "path": str(Path(e.path).resolve())})
            elif e.kind == "connector" and e.connector:
                # Claude Code loads it from claude.ai; we only decide who may use which tool
                name = server_key(e.connector)
                ts.read_only_servers[name] = list(READ_PATTERNS)
                ts.server_ids[name] = e.id
        # connectors this agent was not given stay hidden; with none, they are not loaded at all
        chosen = set(ts.read_only_servers)
        others = [server_key(e.connector) for e in self.entries if e.kind == "connector" and e.connector]
        ts.disallowed_tools = [f"mcp__{s}" for s in others if s not in chosen]
        if not chosen:
            ts.env = dict(DISABLE_ENV)
        ts.tools = list(dict.fromkeys(ts.tools))
        ts.allowed_tools = list(dict.fromkeys(ts.allowed_tools))
        return ts

    def prompt_lines(self, config) -> str:
        return "\n".join(f"- {e.id}: {e.description} (risk: {e.risk})" for e in self.available(config))


def _entry_from_dict(d: dict) -> Entry:
    e = Entry(
        id=str(d["id"]), kind=d.get("kind", "builtin"), description=d.get("description", ""),
        risk=d.get("risk", "read"), tools=list(d.get("tools", [])), server=d.get("server"),
        path=d.get("path"), outward_tools=list(d.get("outward_tools", [])),
        enabled=bool(d.get("enabled", True)), requires=d.get("requires"),
    )
    if e.risk not in RISKS:
        raise ValueError(f"catalog entry {e.id}: risk must be one of {RISKS}")
    if e.kind == "mcp" and e.server:
        missing: set = set()
        _substitute(e.server, missing)
        if missing:
            e.unavailable = "set " + ", ".join(sorted(missing)) + " in .env"
    if e.kind == "plugin" and e.path and not Path(e.path).exists():
        e.unavailable = f"plugin folder {e.path} not found"
    return e


def discover_plugins(plugins_dir: Path) -> list[Entry]:
    """Each folder in plugins/ with .claude-plugin/plugin.json becomes a 'plugin.<name>' entry."""
    out = []
    if not plugins_dir.is_dir():
        return out
    for p in sorted(plugins_dir.iterdir()):
        manifest = p / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        try:
            info = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            continue
        out.append(Entry(id=f"plugin.{p.name}", kind="plugin", path=str(p),
                         description=info.get("description") or f"Claude Code plugin {p.name}",
                         risk=info.get("orchestra_risk", "write")))
    return out


def load_catalog(path: Path | None = None, plugins_dir: Path | None = None) -> Catalog:
    path = Path(path) if path else DEFAULT_CATALOG_PATH
    raw = json.loads(path.read_text()) if path.exists() else BUILTIN_ENTRIES
    entries = [_entry_from_dict(d) for d in raw]
    known = {e.id for e in entries}
    entries += [e for e in discover_plugins(Path(plugins_dir) if plugins_dir else DEFAULT_PLUGINS_DIR)
                if e.id not in known]
    return Catalog(entries)
