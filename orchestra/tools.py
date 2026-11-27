"""The orchestrator's tools: create_agent, assign_task, view_board, finish.

Each handler is a plain async function (easy to test), wrapped as an in-process MCP tool.
"""

import asyncio
import json
import re
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import checks, prompts
from .approvals import make_can_use_tool
from .catalog import Catalog, load_catalog
from .config import TIERS, clamp_tier, step_up
from .playbooks import Playbook, load_playbooks
from .runner import run_agent as default_runner
from .state import AgentSpec, RunState, Task

SERVER_NAME = "orchestra"
TOOL_NAMES = ["read_playbook", "create_agent", "assign_task", "assign_tasks", "view_board", "finish"]
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
        self._owned: dict[str, str] = {}   # file path -> running task that owns it

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

    def _validate(self, args: dict, batch: dict | None = None) -> tuple[dict | None, str]:
        """Check one task's arguments without side effects. Returns (spec, error)."""
        s, cfg = self.s, self.s.config
        batch = batch or {}
        agent_name = args.get("agent", "")
        task_id = str(args.get("task_id", "")).strip()
        title = str(args.get("title", "") or "").strip()
        task_text = str(args.get("task", ""))
        done_when = str(args.get("done_when", ""))
        replaces = str(args.get("replaces", "") or "").strip()
        task_checks = args.get("checks") or []
        checks_only = bool(args.get("checks_only", False))
        depends_on = [str(d).strip() for d in (args.get("depends_on") or []) if str(d).strip()]
        owns = [str(o).strip().lstrip("./") for o in (args.get("owns") or []) if str(o).strip()]

        if agent_name not in s.agents:
            return None, f"No agent '{agent_name}'. Existing: {list(s.agents)}. Create it first."
        if not task_id or not task_text or not done_when:
            return None, "task_id, task and done_when are all required"
        if not title:
            return None, 'title is required: 2 to 4 words naming the task, like "Compare fees"'
        if task_id in s.board and s.board[task_id].status == "done":
            return None, f"Task '{task_id}' is already done. Use a new task_id for new work."
        if task_id in s.board and s.board[task_id].status in ("pending", "running", "checking", "retrying"):
            return None, f"Task '{task_id}' is already on the board. Use a new task_id."
        if replaces and (replaces not in s.board or s.board[replaces].status != "failed"):
            return None, (f"'replaces' must name a failed task. Failed tasks: "
                          f"{[k for k, v in s.board.items() if v.status == 'failed']}")
        if bad := checks.validate(task_checks, cfg.allow_bash):
            return None, bad
        if checks_only and not task_checks:
            return None, "checks_only needs at least one check"
        for d in depends_on:
            if d == task_id:
                return None, f"Task '{task_id}' can't depend on itself"
            if d not in batch and d not in s.board:
                return None, f"'{task_id}' depends on unknown task '{d}'"
            if d not in batch and s.board[d].status != "done":
                return None, f"'{task_id}' depends on '{d}', which is {s.board[d].status}. Only done tasks or tasks in this batch."
        agent = s.agents[agent_name]
        tier, tier_reason, problem = self._pick_tier(args, agent.model or cfg.worker_model)
        if problem:
            return None, problem
        if not args.get("tier") and cfg.pick_tier:
            tier_reason = agent.tier_reason  # inherited from the agent
        return {"agent": agent_name, "task_id": task_id, "title": title[:60], "task": task_text,
                "done_when": done_when, "replaces": replaces, "checks": task_checks, "checks_only": checks_only,
                "tier": tier, "tier_reason": tier_reason, "depends_on": depends_on, "owns": owns}, ""

    def _owner_conflict(self, spec: dict) -> str:
        """A file this task owns that a running task already owns."""
        for path in spec["owns"]:
            other = self._owned.get(path)
            if other and other != spec["task_id"]:
                return f"'{path}' is owned by running task '{other}'. Two tasks can't own the same file at once."
        return ""

    def _register(self, spec: dict) -> Task:
        s = self.s
        s.usage.assignments += 1
        t = Task(task_id=spec["task_id"], agent=spec["agent"], task=spec["task"], done_when=spec["done_when"],
                 title=spec["title"], status="pending", replaces=spec["replaces"], tier=spec["tier"],
                 tier_reason=spec["tier_reason"], depends_on=spec["depends_on"], owns=spec["owns"])
        s.board[t.task_id] = t
        s.log("task_assigned", task_id=t.task_id, title=t.title, agent=t.agent, task=t.task,
              done_when=t.done_when, replaces=t.replaces, tier=t.tier, tier_reason=t.tier_reason,
              checks=[checks.label(c) for c in spec["checks"]], checks_only=spec["checks_only"],
              depends_on=t.depends_on, owns=t.owns)
        return t

    async def assign_task(self, args: dict) -> dict:
        s = self.s
        spec, problem = self._validate(args)
        if problem:
            return _err(problem)
        if problem := self._owner_conflict(spec):
            return _err(problem)
        if problem := s.budget_problem():
            s.log("budget_exhausted", reason=problem)
            return _err(f"Out of budget: {problem}. Call finish with give_up=true.")
        t = self._register(spec)
        return await self._run_task(t, spec)

    # ---- assign_tasks: several tasks, run in parallel where dependencies allow ----

    async def assign_tasks(self, args: dict) -> dict:
        s, b = self.s, self.s.config.budget
        items = args.get("tasks") or []
        if not isinstance(items, list) or not items:
            return _err("tasks must be a non-empty list")
        ids = [str(i.get("task_id", "")).strip() for i in items]
        if len(set(ids)) != len(ids):
            return _err(f"task_id values must be unique in a batch: {ids}")
        batch = dict(zip(ids, items))
        specs: dict[str, dict] = {}
        for tid, item in batch.items():
            spec, problem = self._validate(item, batch)
            if problem:
                return _err(f"Batch refused, nothing started. {problem}")
            specs[tid] = spec
        if cycle := _find_cycle({k: [d for d in v["depends_on"] if d in specs] for k, v in specs.items()}):
            return _err(f"Batch refused: dependency loop {' -> '.join(cycle)}")
        after = _ancestors({k: [d for d in v["depends_on"] if d in specs] for k, v in specs.items()})
        for a in specs:
            for c in specs:
                if a < c and a not in after[c] and c not in after[a]:
                    shared = set(specs[a]["owns"]) & set(specs[c]["owns"])
                    if shared:
                        return _err(f"Batch refused: '{a}' and '{c}' may run at once and both own {sorted(shared)}. "
                                    "Split the files, or make one depend on the other.")
        for spec in specs.values():
            if problem := self._owner_conflict(spec):
                return _err(f"Batch refused: {problem}")
        if problem := s.budget_problem():
            s.log("budget_exhausted", reason=problem)
            return _err(f"Out of budget: {problem}. Call finish with give_up=true.")
        left = b.max_assignments - s.usage.assignments
        if len(specs) > left:
            return _err(f"Batch refused: {len(specs)} tasks but only {left} assignments left. Send fewer.")

        tasks = {tid: self._register(spec) for tid, spec in specs.items()}
        results: dict[str, str] = {}      # task_id -> PASSED / FAILED / NOT STARTED, with text
        waiting = list(specs)
        running: dict[asyncio.Task, str] = {}
        busy_agents: set[str] = set()

        def block(tid: str, why: str) -> None:
            t = tasks[tid]
            t.status, t.feedback, t.short = "failed", why, "not started"
            s.log("task_failed", task_id=tid, attempts=0, reason=why)
            results[tid] = f"NOT STARTED: {why}"

        try:
            while waiting or running:
                for tid in list(waiting):
                    deps = specs[tid]["depends_on"]
                    # deps are batch tasks (tracked in results) or tasks already done before the batch
                    bad = [d for d in deps if d in results and not results[d].startswith("PASSED")]
                    if bad:
                        waiting.remove(tid)
                        block(tid, f"depends on {', '.join(bad)}, which did not pass")
                        continue
                    if len(running) >= max(1, b.max_parallel):
                        break
                    if any(s.board[d].status != "done" for d in deps) or specs[tid]["agent"] in busy_agents:
                        continue
                    if problem := s.budget_problem():
                        waiting.remove(tid)
                        block(tid, f"out of budget: {problem}")
                        continue
                    waiting.remove(tid)
                    busy_agents.add(specs[tid]["agent"])
                    job = asyncio.create_task(self._run_task(tasks[tid], specs[tid]), name=f"task-{tid}")
                    running[job] = tid
                if not running:
                    for tid in waiting:  # nothing can start: should not happen after validation
                        block(tid, "its dependencies can't run")
                    break
                done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for job in done:
                    tid = running.pop(job)
                    busy_agents.discard(specs[tid]["agent"])
                    res = job.result()
                    results[tid] = text_of(res)
        finally:  # stop cancels every running task
            for job in running:
                job.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)

        passed = sum(1 for r in results.values() if r.startswith("PASSED"))
        body = "\n\n".join(f"## {tid}\n{results.get(tid, 'NOT STARTED')[:MAX_OUTPUT_BACK // max(1, len(ids))]}"
                            for tid in ids)
        summary = f"{passed} of {len(ids)} tasks passed.\n\n{body}"
        return _ok(summary) if passed == len(ids) else _err(summary)

    # ---- the inner retry + verify loop for one registered task ----------------

    async def _run_task(self, t: Task, spec: dict) -> dict:
        """Hold the task's files while it runs, then release them."""
        for path in t.owns:
            self._owned[path] = t.task_id
        try:
            return await self._attempts(t, spec["checks"], spec["checks_only"])
        finally:
            for path in t.owns:
                if self._owned.get(path) == t.task_id:
                    del self._owned[path]

    async def _attempts(self, t: Task, task_checks: list[dict], checks_only: bool) -> dict:
        s, b, cfg = self.s, self.s.config.budget, self.s.config
        task_id, agent_name, task_text, done_when, replaces = t.task_id, t.agent, t.task, t.done_when, t.replaces
        agent = s.agents[agent_name]
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
            self._report_new_files(before, reported, task_id, agent_name, t.owns)

            verdict, by, results = None, "model", None
            if work.is_error and not work.text:
                fb, short, by = f"Worker errored: {work.error}", "worker errored", "worker"
            else:
                if task_checks:  # 2a. cheap checks first: no model call
                    ok, results = await checks.run_checks(task_checks, s.workspace)
                    if not ok:
                        verdict, by = {"passed": False}, "checks"
                        fb, short = checks.failure_text(results)
                    elif checks_only:
                        verdict, by = {"passed": True}, "checks"
                        fb = "All checks passed: " + "; ".join(r["check"] for r in results)
                        short = f"{len(results)} checks passed"
                if verdict is None:  # 2b. independent model checker verifies against done_when
                    t.status = "checking"
                    s.log("checker_started", task_id=task_id, attempt=attempt)
                    check = await self.runner(
                        prompt=prompts.checker_task_prompt(task_text, done_when, work.text, results),
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
                    fb = verdict.get("reason", "") or ""
                    short = (verdict.get("short") or prompts.short_reason(fb))[:60]
                extra = {"checked_by": by, **({"checks": results} if results else {})}
                if verdict.get("passed"):
                    t.status, t.feedback, t.short = "done", fb, short
                    s.log("task_passed", task_id=task_id, attempt=attempt, reason=fb, short=short, **extra)
                    if replaces:  # the failed task this one superseded no longer blocks finish
                        s.board[replaces].status = "replaced"
                        s.board[replaces].replaced_by = task_id
                        s.log("task_replaced", task_id=replaces, by=task_id)
                    s.save_board()
                    return _ok(
                        f"PASSED on attempt {attempt}.\nChecker: {t.feedback}\n\n"
                        f"Worker report:\n{work.text[:MAX_OUTPUT_BACK]}"
                    )
                fb = fb or "Checker gave no reason"
                # it failed on its tier: the next try moves one tier up, once
                if (attempt < b.max_attempts_per_task and not stepped_up
                        and (nxt := step_up(t.tier, cfg.max_tier))):
                    t.tier, stepped_up = nxt, True

            feedback.append(fb)
            t.feedback, t.short = fb, short
            t.status = "retrying"
            s.log("attempt_failed", task_id=task_id, attempt=attempt, reason=fb, short=short,
                  checked_by=by, **({"checks": results} if results else {}))
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

    def _report_new_files(self, before: dict, reported: set, task_id: str, agent: str,
                          owns: list[str] | None = None) -> None:
        """Files made or changed through Bash (not seen as Write/Edit calls).

        With parallel tasks the scan sees every task's files, so a task that owns files only
        reports changes inside them."""
        after = snapshot(self.s.workspace)
        for path, mtime in after.items():
            if path in reported:
                continue
            if owns and not any(path == o or path.startswith(o.rstrip("/") + "/") for o in owns):
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

        task_props = {
            "agent": {"type": "string"},
            "task_id": {"type": "string", "description": "Unique id, e.g. research-1"},
            "title": {"type": "string", "description": "2 to 4 words shown to the user, e.g. Compare fees"},
            "task": {"type": "string", "description": "Exact instructions, inputs, and output file names"},
            "done_when": {"type": "string", "description": "Concrete criteria a checker can verify from files"},
            "replaces": {"type": "string", "description": "Optional: id of a FAILED task this one supersedes"},
            "checks": checks.SCHEMA,
            "checks_only": {"type": "boolean", "description": "true if the checks cover all of done_when: passing checks pass the task with no model checker"},
            "tier": {"type": "string", "enum": TIERS,
                     "description": "Optional, defaults to the agent's tier. Model: haiku for search, reading, summaries, simple edits; sonnet for writing, planning, code; opus only after a task failed on sonnet"},
            "tier_reason": {"type": "string", "description": "A few words on why this tier, shown to the user"},
            "depends_on": {"type": "array", "items": {"type": "string"},
                           "description": "task_ids that must pass first: in the same batch, or already done"},
            "owns": {"type": "array", "items": {"type": "string"},
                     "description": "Files or folders only this task writes while it runs, e.g. research/gopay.md"},
        }
        required = ["agent", "task_id", "title", "task", "done_when"]

        assign = tool(
            "assign_task",
            "Give one task to an agent. It is retried and independently verified. Returns PASSED or FAILED.",
            {"type": "object", "properties": task_props, "required": required},
        )(self.assign_task)

        assign_many = tool(
            "assign_tasks",
            "Give several tasks at once. Tasks whose depends_on have passed run in parallel (up to the run's limit); "
            "each is retried and verified like assign_task. Returns every result when all have ended.",
            {
                "type": "object",
                "properties": {"tasks": {"type": "array", "items": {"type": "object", "properties": task_props,
                                                                   "required": required}}},
                "required": ["tasks"],
            },
        )(self.assign_tasks)

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

        return create_sdk_mcp_server(name=SERVER_NAME, tools=[read, create, assign, assign_many, board, fin])


def _parse_verdict(text: str) -> dict:
    """Fallback if structured output is missing: look for JSON in the text."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"passed": False, "reason": f"Checker returned no verdict: {(text or '')[:300]}"}


def text_of(res: dict) -> str:
    return res["content"][0]["text"]


def _ancestors(deps: dict[str, list[str]]) -> dict[str, set[str]]:
    """Every task each task waits for, directly or not."""
    out: dict[str, set[str]] = {}

    def walk(k: str, seen: set[str]) -> set[str]:
        if k in out:
            return out[k]
        acc: set[str] = set()
        for d in deps.get(k, []):
            if d in seen:
                continue
            acc |= {d} | walk(d, seen | {d})
        out[k] = acc
        return acc

    for k in deps:
        walk(k, {k})
    return out


def _find_cycle(deps: dict[str, list[str]]) -> list[str]:
    """A dependency loop as a list of ids (first repeated at the end), or []."""
    state: dict[str, int] = {}
    path: list[str] = []

    def visit(k: str) -> list[str]:
        state[k] = 1
        path.append(k)
        for d in deps.get(k, []):
            if state.get(d) == 1:
                return path[path.index(d):] + [d]
            if state.get(d) is None and (c := visit(d)):
                return c
        state[k] = 2
        path.pop()
        return []

    for k in deps:
        if state.get(k) is None and (c := visit(k)):
            return c
    return []
