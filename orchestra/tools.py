"""The orchestrator's tools: create_agent, assign_task, view_board, finish.

Each handler is a plain async function (easy to test), wrapped as an in-process MCP tool.
"""

import json
import re

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import prompts
from .runner import run_agent as default_runner
from .state import AgentSpec, RunState, Task

SERVER_NAME = "orchestra"
TOOL_NAMES = ["create_agent", "assign_task", "view_board", "finish"]
MCP_TOOL_NAMES = [f"mcp__{SERVER_NAME}__{n}" for n in TOOL_NAMES]

MAX_OUTPUT_BACK = 3000  # chars of worker output returned to the orchestrator


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


class OrchestraTools:
    def __init__(self, state: RunState, runner=default_runner):
        self.s = state
        self.runner = runner

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

        registry = s.config.tool_registry()
        requested = list(dict.fromkeys(args.get("tools") or []))
        unknown = [t for t in requested if t not in registry]
        if unknown:
            return _err(f"Unknown tools {unknown}. Choose only from: {list(registry)}")

        spec = AgentSpec(
            name=name,
            role=str(args.get("role", "")),
            system_prompt=str(args.get("system_prompt", "")),
            tools=requested,
        )
        s.agents[name] = spec
        s.log("agent_created", name=name, role=spec.role, tools=requested)
        s.save_board()
        return _ok(f"Created agent '{name}' with tools {requested}.")

    # ---- assign_task: the inner retry + verify loop ------------------------

    async def assign_task(self, args: dict) -> dict:
        s, b, cfg = self.s, self.s.config.budget, self.s.config
        agent_name = args.get("agent", "")
        task_id = str(args.get("task_id", "")).strip()
        task_text = str(args.get("task", ""))
        done_when = str(args.get("done_when", ""))
        replaces = str(args.get("replaces", "") or "").strip()

        if agent_name not in s.agents:
            return _err(f"No agent '{agent_name}'. Existing: {list(s.agents)}. Create it first.")
        if not task_id or not task_text or not done_when:
            return _err("task_id, task and done_when are all required")
        if task_id in s.board and s.board[task_id].status == "done":
            return _err(f"Task '{task_id}' is already done. Use a new task_id for new work.")
        if replaces and (replaces not in s.board or s.board[replaces].status != "failed"):
            return _err(f"'replaces' must name a failed task. Failed tasks: "
                        f"{[k for k, v in s.board.items() if v.status == 'failed']}")
        if problem := s.budget_problem():
            s.log("budget", reason=problem)
            return _err(f"Out of budget: {problem}. Call finish with give_up=true.")

        s.usage.assignments += 1
        agent = s.agents[agent_name]
        t = Task(task_id=task_id, agent=agent_name, task=task_text, done_when=done_when,
                 status="running", replaces=replaces)
        s.board[task_id] = t
        s.log("task_assigned", task_id=task_id, agent=agent_name, done_when=done_when)

        feedback: list[str] = []
        for attempt in range(1, b.max_attempts_per_task + 1):
            t.attempts = attempt
            s.log("attempt_started", task_id=task_id, agent=agent_name, attempt=attempt,
                  max_attempts=b.max_attempts_per_task)

            # 1. worker does the task
            work = await self.runner(
                prompt=prompts.worker_task_prompt(task_text, done_when, feedback),
                system_prompt=agent.system_prompt,
                tools=agent.tools,
                model=cfg.worker_model,
                cwd=s.workspace,
                max_turns=b.max_worker_turns,
            )
            s.record_usage(work.turns, work.cost_usd)
            t.output = work.text
            if work.is_error and not work.text:
                fb = f"Worker errored: {work.error}"
            else:
                # 2. independent checker verifies against done_when
                check = await self.runner(
                    prompt=prompts.checker_task_prompt(task_text, done_when, work.text),
                    system_prompt=prompts.CHECKER_PROMPT,
                    tools=cfg.checker_tools(),
                    model=cfg.checker_model,
                    cwd=s.workspace,
                    max_turns=15,
                    output_schema=prompts.CHECKER_SCHEMA,
                )
                s.record_usage(check.turns, check.cost_usd)
                verdict = check.structured if isinstance(check.structured, dict) else _parse_verdict(check.text)
                if verdict.get("passed"):
                    t.status, t.feedback = "done", verdict.get("reason", "")
                    s.log("task_passed", task_id=task_id, attempt=attempt, reason=t.feedback)
                    if replaces:  # the failed task this one superseded no longer blocks finish
                        s.board[replaces].status = "replaced"
                        s.log("task_replaced", task_id=replaces, by=task_id)
                    s.save_board()
                    return _ok(
                        f"PASSED on attempt {attempt}.\nChecker: {t.feedback}\n\n"
                        f"Worker report:\n{work.text[:MAX_OUTPUT_BACK]}"
                    )
                fb = verdict.get("reason") or "Checker gave no reason"

            feedback.append(fb)
            t.feedback = fb
            s.log("attempt_failed", task_id=task_id, attempt=attempt, reason=fb)
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
        s.status = "gave_up" if give_up else "finished"
        s.log("finished", give_up=give_up, tasks=len(s.board))
        s.save_board()
        return _ok("Accepted. The run is complete, stop now.")

    # ---- MCP server ---------------------------------------------------------

    def mcp_server(self):
        registry = list(self.s.config.tool_registry())

        create = tool(
            "create_agent",
            "Create a new worker agent with its own role, system prompt, and tools.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short unique id, e.g. researcher"},
                    "role": {"type": "string", "description": "One line describing the specialty"},
                    "system_prompt": {"type": "string", "description": "Full instructions for this agent"},
                    "tools": {"type": "array", "items": {"type": "string", "enum": registry}},
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
                    "task": {"type": "string", "description": "Exact instructions, inputs, and output file names"},
                    "done_when": {"type": "string", "description": "Concrete criteria a checker can verify from files"},
                    "replaces": {"type": "string", "description": "Optional: id of a FAILED task this one supersedes"},
                },
                "required": ["agent", "task_id", "task", "done_when"],
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

        return create_sdk_mcp_server(name=SERVER_NAME, tools=[create, assign, board, fin])


def _parse_verdict(text: str) -> dict:
    """Fallback if structured output is missing: look for JSON in the text."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"passed": False, "reason": f"Checker returned no verdict: {(text or '')[:300]}"}
