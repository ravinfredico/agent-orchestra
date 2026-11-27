"""The orchestrator's tools: create_agent, assign_task, view_board, finish.

Each handler is a plain async function (easy to test), wrapped as an in-process MCP tool.
"""

import json
import re
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import prompts
from .approvals import make_can_use_tool
from .catalog import Catalog, load_catalog
from .config import TIERS, clamp_tier, step_up
from .playbooks import Playbook, load_playbooks
from .runner import run_agent as default_runner
from .state import AgentSpec, RunState, Task

SERVER_NAME = "orchestra"
TOOL_NAMES = ["read_playbook", "create_agent", "assign_task", "view_board", "finish"]
MCP_TOOL_NAMES = [f"mcp__{SERVER_NAME}__{n}" for n in TOOL_NAMES]

MAX_OUTPUT_BACK = 3000  # chars of worker output returned to the orchestrator
SCAN_SKIP = {".git", ".agents", "node_modules", "__pycache__", ".venv"}


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


# ---- live activity ---------------------------------------------------------

def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return str(path)


def activity_summary(tool_name: str, tool_input: dict, root: Path) -> str:
    """One short line for the UI: 'reading research/dana.md'."""
    i = tool_input or {}
    p = i.get("file_path") or i.get("path") or ""
    if tool_name == "Read":
        s = f"reading {_rel(p, root)}"
    elif tool_name == "Write":
        s = f"writing {_rel(p, root)}"
    elif tool_name == "Edit":
        s = f"editing {_rel(p, root)}"
    elif tool_name in ("Glob", "Grep"):
        s = f"searching files for {i.get('pattern', '')}"
    elif tool_name == "WebSearch":
        s = f'searching the web for "{i.get("query", "")}"'
    elif tool_name == "WebFetch":
        s = f"reading {re.sub(r'^https?://', '', str(i.get('url', '')))}"
    elif tool_name == "Bash":
        s = f"running {str(i.get('command', '')).splitlines()[0] if i.get('command') else 'a command'}"
    elif tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        s = f"using {parts[1]}: {parts[-1].replace('_', ' ')}"
    else:
        s = f"using {tool_name}"
    return s if len(s) <= 80 else s[:79] + "…"


def snapshot(root: Path) -> dict[str, float]:
    """mtime of every file in the workspace, skipping tool folders."""
    out = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if any(part in SCAN_SKIP for part in p.relative_to(root).parts):
            continue
        if p.is_file():
            try:
                out[str(p.relative_to(root))] = p.stat().st_mtime
            except OSError:
                pass
    return out


class OrchestraTools:
    def __init__(self, state: RunState, runner=default_runner, catalog: Catalog | None = None,
                 playbooks: dict[str, Playbook] | None = None):
        self.s = state
        self.runner = runner
        self.catalog = catalog or load_catalog()
        self.playbooks = playbooks if playbooks is not None else load_playbooks()

    # ---- read_playbook ------------------------------------------------------

    async def read_playbook(self, args: dict) -> dict:
        pid = str(args.get("id", "")).strip()
        book = self.playbooks.get(pid)
        if not book:
            return _err(f"No playbook '{pid}'. Choose one of: {list(self.playbooks)}")
        self.s.log("playbook_chosen", id=book.id, title=book.title)
        return _ok(f"# Playbook: {book.title}\n{book.when}\n\n{book.body}")

    # ---- create_agent -------------------------------------------------------

    async def create_agent(self, args: dict) -> dict:
        s, b = self.s, self.s.config.budget
        name = re.sub(r"[^a-zA-Z0-9_-]", "_", str(args.get("name", "")).strip())
        if not name:
            return _err("name is required")
        if name in s.agents:
            return _err(f"Agent '{name}' already exists. Pick a new name or reuse it.")
        if len(s.agents) >= b.max_agents:
            return _err(f"Agent limit reached ({b.max_agents}). Reuse existing agents: {list(s.agents)}")

        available = self.catalog.available_ids(s.config)
        requested = list(dict.fromkeys(args.get("tools") or []))
        unknown = [t for t in requested if t not in available]
        if unknown:
            return _err(f"Unknown tools {unknown}. Choose only from the catalog: {available}")

        tier, tier_reason, problem = self._pick_tier(args, s.config.worker_model)
        if problem:
            return _err(problem)
        spec = AgentSpec(
            name=name,
            role=str(args.get("role", "")),
            system_prompt=str(args.get("system_prompt", "")),
            tools=requested,
            color_index=len(s.agents),
            model=tier,
            tier_reason=tier_reason,
        )
        s.agents[name] = spec
        s.log("agent_created", name=name, role=spec.role, tools=requested, model=spec.model,
              tier_reason=tier_reason, color_index=spec.color_index)
        s.save_board()
        return _ok(f"Created agent '{name}' with tools {requested}.")

    def _pick_tier(self, args: dict, default: str) -> tuple[str, str, str]:
        """(tier, reason, error). With pick_tier off, the run's worker model always wins."""
        cfg = self.s.config
        asked = str(args.get("tier", "") or "").strip().lower()
        if asked and asked not in TIERS:
            return "", "", f"tier must be one of {TIERS}"
        if not cfg.pick_tier:
            return clamp_tier(cfg.worker_model, cfg.max_tier), "set by the run", ""
        tier = clamp_tier(asked or default, cfg.max_tier)
        reason = str(args.get("tier_reason", "") or "").strip()[:120]
        return tier, reason, ""

    # ---- assign_task: the inner retry + verify loop ------------------------

    async def assign_task(self, args: dict) -> dict:
        s, b, cfg = self.s, self.s.config.budget, self.s.config
        agent_name = args.get("agent", "")
        task_id = str(args.get("task_id", "")).strip()
        title = str(args.get("title", "") or "").strip()
        task_text = str(args.get("task", ""))
        done_when = str(args.get("done_when", ""))
        replaces = str(args.get("replaces", "") or "").strip()

        if agent_name not in s.agents:
            return _err(f"No agent '{agent_name}'. Existing: {list(s.agents)}. Create it first.")
        if not task_id or not task_text or not done_when:
            return _err("task_id, task and done_when are all required")
        if not title:
            return _err('title is required: 2 to 4 words naming the task, like "Compare fees"')
        if task_id in s.board and s.board[task_id].status == "done":
            return _err(f"Task '{task_id}' is already done. Use a new task_id for new work.")
        if replaces and (replaces not in s.board or s.board[replaces].status != "failed"):
            return _err(f"'replaces' must name a failed task. Failed tasks: "
                        f"{[k for k, v in s.board.items() if v.status == 'failed']}")
        if problem := s.budget_problem():
            s.log("budget_exhausted", reason=problem)
            return _err(f"Out of budget: {problem}. Call finish with give_up=true.")

        agent = s.agents[agent_name]
        tier, tier_reason, problem = self._pick_tier(args, agent.model or cfg.worker_model)
        if problem:
            return _err(problem)
        if not args.get("tier") and cfg.pick_tier:
            tier_reason = agent.tier_reason  # inherited from the agent

        s.usage.assignments += 1
        t = Task(task_id=task_id, agent=agent_name, task=task_text, done_when=done_when,
                 title=title[:60], status="pending", replaces=replaces, tier=tier, tier_reason=tier_reason)
        s.board[task_id] = t
        s.log("task_assigned", task_id=task_id, title=t.title, agent=agent_name, task=task_text,
              done_when=done_when, replaces=replaces, tier=tier, tier_reason=tier_reason)

        toolset = self.catalog.toolset(agent.tools, cfg)
        scratch = s.workspace / ".agents" / agent_name
        scratch.mkdir(parents=True, exist_ok=True)
        sandbox = None
        if "Bash" in toolset.tools:
            sandbox = {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False}
            if cfg.allowed_domains:
                sandbox["network"] = {"allowedDomains": list(cfg.allowed_domains)}

        feedback: list[str] = []
        stepped_up = False
        for attempt in range(1, b.max_attempts_per_task + 1):
            t.attempts = attempt
            t.status = "running" if attempt == 1 else "retrying"
            s.log("attempt_started", task_id=task_id, attempt=attempt, tier=t.tier)

            # 1. worker does the task
            reported: set[str] = set()
            before = snapshot(s.workspace)

            def on_tool_use(tool_name: str, tool_input: dict, _tid=task_id, _agent=agent_name):
                s.log("worker_activity", task_id=_tid, agent=_agent, tool=tool_name,
                      summary=activity_summary(tool_name, tool_input, s.workspace))
                if tool_name in ("Write", "Edit") and tool_input.get("file_path"):
                    rel = _rel(tool_input["file_path"], s.workspace)
                    reported.add(rel)
                    s.log("file_written", task_id=_tid, agent=_agent, path=rel, size=None)

            can_use = None
            if toolset.needs_approval_callback:
                can_use = make_can_use_tool(s.approvals, toolset, agent_name, task_id)

            work = await self.runner(
                prompt=prompts.worker_task_prompt(task_text, done_when, feedback,
                                                  scratch=f".agents/{agent_name}/"),
                system_prompt=agent.system_prompt,
                tools=toolset.tools,
                allowed_tools=toolset.allowed_tools,
                mcp_servers=toolset.mcp_servers or None,
                plugins=toolset.plugins or None,
                can_use_tool=can_use,
                sandbox=sandbox,
                model=t.tier,
                cwd=s.workspace,
                max_turns=b.max_worker_turns,
                on_tool_use=on_tool_use,
            )
            s.record_usage(work.turns, work.cost_usd)
            t.output = work.text
            self._report_new_files(before, reported, task_id, agent_name)

            if work.is_error and not work.text:
                fb, short = f"Worker errored: {work.error}", "worker errored"
            else:
                # 2. independent checker verifies against done_when
                t.status = "checking"
                s.log("checker_started", task_id=task_id, attempt=attempt)
                check = await self.runner(
                    prompt=prompts.checker_task_prompt(task_text, done_when, work.text),
                    system_prompt=prompts.CHECKER_PROMPT,
                    tools=cfg.checker_tools(),
                    model=cfg.checker_model,
                    cwd=s.workspace,
                    max_turns=15,
                    output_schema=prompts.CHECKER_SCHEMA,
                    sandbox=sandbox,
                )
                s.record_usage(check.turns, check.cost_usd)
                verdict = check.structured if isinstance(check.structured, dict) else _parse_verdict(check.text)
                reason = verdict.get("reason", "") or ""
                short = (verdict.get("short") or prompts.short_reason(reason))[:60]
                if verdict.get("passed"):
                    t.status, t.feedback, t.short = "done", reason, short
                    s.log("task_passed", task_id=task_id, attempt=attempt, reason=reason, short=short)
                    if replaces:  # the failed task this one superseded no longer blocks finish
                        s.board[replaces].status = "replaced"
                        s.board[replaces].replaced_by = task_id
                        s.log("task_replaced", task_id=replaces, by=task_id)
                    s.save_board()
                    return _ok(
                        f"PASSED on attempt {attempt}.\nChecker: {t.feedback}\n\n"
                        f"Worker report:\n{work.text[:MAX_OUTPUT_BACK]}"
                    )
                fb = reason or "Checker gave no reason"
                # it failed on its tier: the next try moves one tier up, once
                if (attempt < b.max_attempts_per_task and not stepped_up
                        and (nxt := step_up(t.tier, cfg.max_tier))):
                    t.tier, stepped_up = nxt, True

            feedback.append(fb)
            t.feedback, t.short = fb, short
            t.status = "retrying"
            s.log("attempt_failed", task_id=task_id, attempt=attempt, reason=fb, short=short)
            if s.budget_problem():
                break

        t.status = "failed"
        s.log("task_failed", task_id=task_id, attempts=t.attempts)
        s.save_board()
        return _err(
            f"FAILED after {t.attempts} attempts.\nLast feedback: {t.feedback}\n\n"
            "Fix the cause before retrying: rewrite or split the task, adjust tools, or create a "
            f"better-suited agent, then assign again with a new task_id and replaces='{task_id}'."
        )

    def _report_new_files(self, before: dict, reported: set, task_id: str, agent: str) -> None:
        """Files made or changed through Bash (not seen as Write/Edit calls)."""
        after = snapshot(self.s.workspace)
        for path, mtime in after.items():
            if path in reported:
                continue
            if path not in before or before[path] != mtime:
                size = (self.s.workspace / path).stat().st_size if (self.s.workspace / path).exists() else None
                self.s.log("file_written", task_id=task_id, agent=agent, path=path, size=size)

    # ---- view_board ---------------------------------------------------------

    async def view_board(self, args: dict) -> dict:
        return _ok(json.dumps(self.s.board_summary(), indent=2))

    # ---- finish: refuses until everything is done ---------------------------

    async def finish(self, args: dict) -> dict:
        s = self.s
        result = str(args.get("result", "")).strip()
        give_up = bool(args.get("give_up", False))
        if not result:
            return _err("result is required")
        if not s.board:
            return _err("No tasks have been run yet. Plan, create agents, and assign tasks first.")
        pending = s.unfinished()
        if pending and not give_up:
            ids = [f"{t.task_id} ({t.status})" for t in pending]
            return _err(
                f"Refused: not every task is done: {ids}. Retry or replace them. "
                "Only use give_up=true if the budget is exhausted."
            )
        if give_up and not s.budget_problem() and pending:
            return _err("give_up is only allowed once the budget is exhausted. Keep working.")
        s.final_result = result
        # logged by the outer loop once the orchestrator's turn (and its usage) has ended,
        # so `finished` is always the last event in the log
        s.pending_finish = {"give_up": give_up, "result": result, "tasks": len(s.board)}
        s.save_board()
        return _ok("Accepted. The run is complete, stop now.")

    # ---- MCP server ---------------------------------------------------------

    def mcp_server(self):
        available = self.catalog.available_ids(self.s.config)

        read = tool(
            "read_playbook",
            "Read the playbook for one kind of task: steps, done-when templates, pitfalls.",
            {
                "type": "object",
                "properties": {"id": {"type": "string", "enum": list(self.playbooks)}},
                "required": ["id"],
            },
        )(self.read_playbook)

        create = tool(
            "create_agent",
            "Create a new worker agent: any specialist the task needs, with its own role, system prompt, and catalog tools.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short unique id, e.g. researcher"},
                    "role": {"type": "string", "description": "One line describing the specialty"},
                    "system_prompt": {"type": "string", "description": "Full instructions for this agent"},
                    "tools": {"type": "array", "items": {"type": "string", "enum": available}},
                    "tier": {"type": "string", "enum": TIERS,
                             "description": "Model: haiku for search, reading, summaries, simple edits; sonnet for writing, planning, code; opus only after a task failed on sonnet"},
                    "tier_reason": {"type": "string", "description": "A few words on why this tier, shown to the user"},
                },
                "required": ["name", "role", "system_prompt", "tools"],
            },
        )(self.create_agent)

        assign = tool(
            "assign_task",
            "Give a task to an agent. It is retried and independently verified. Returns PASSED or FAILED.",
            {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "task_id": {"type": "string", "description": "Unique id, e.g. research-1"},
                    "title": {"type": "string", "description": "2 to 4 words shown to the user, e.g. Compare fees"},
                    "task": {"type": "string", "description": "Exact instructions, inputs, and output file names"},
                    "done_when": {"type": "string", "description": "Concrete criteria a checker can verify from files"},
                    "replaces": {"type": "string", "description": "Optional: id of a FAILED task this one supersedes"},
                    "tier": {"type": "string", "enum": TIERS,
                             "description": "Optional, defaults to the agent's tier. Model: haiku for search, reading, summaries, simple edits; sonnet for writing, planning, code; opus only after a task failed on sonnet"},
                    "tier_reason": {"type": "string", "description": "A few words on why this tier, shown to the user"},
                },
                "required": ["agent", "task_id", "title", "task", "done_when"],
            },
        )(self.assign_task)

        board = tool(
            "view_board", "Show all tasks, statuses, feedback, and remaining budget.",
            {"type": "object", "properties": {}},
        )(self.view_board)

        fin = tool(
            "finish",
            "Submit the final result. Refused unless every task is done (or budget is exhausted and give_up=true).",
            {
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "Final summary and list of deliverable files"},
                    "give_up": {"type": "boolean", "default": False},
                },
                "required": ["result"],
            },
        )(self.finish)

        return create_sdk_mcp_server(name=SERVER_NAME, tools=[read, create, assign, board, fin])


def _parse_verdict(text: str) -> dict:
    """Fallback if structured output is missing: look for JSON in the text."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"passed": False, "reason": f"Checker returned no verdict: {(text or '')[:300]}"}
