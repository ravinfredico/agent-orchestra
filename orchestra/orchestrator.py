"""The outer loop: run the orchestrator until it calls finish or the budget runs out.

    state = create_run(task, config)          # returns at once with a run id and run_started logged
    await execute_run(state)                  # the actual work; cancel the task to stop

`run()` does both, for the CLI.
"""

import asyncio
import json
import shutil
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from . import prompts
from .approvals import ApprovalBroker
from .connectors import DISABLE_ENV
from .connectors import discover as discover_connectors
from .catalog import Catalog, load_catalog, with_connectors
from .config import Config
from .playbooks import summary_lines
from .runner import run_agent as default_runner
from .state import RunState, make_run_id
from .tools import MCP_TOOL_NAMES, SERVER_NAME, OrchestraTools

COPY_IGNORE = shutil.ignore_patterns(".agents", ".git", "node_modules", "__pycache__", ".venv")


def create_run(task: str, config: Config, runs_dir: Path = Path("runs"), workspace: Path | None = None, *,
               repo: str | None = None, branch: str | None = None, parent_id: str | None = None,
               seed_from: Path | None = None, listeners=None, run_id: str | None = None,
               team: dict | None = None, trigger: dict | None = None) -> RunState:
    """Make the run folder and state, copy a seed workspace if given, and log run_started."""
    run_dir = Path(runs_dir) / (run_id or make_run_id())
    while not run_id and run_dir.exists():          # never reuse a folder
        run_dir = Path(runs_dir) / make_run_id()
    state = RunState(task, config, run_dir, workspace, repo=repo, branch=branch,
                     parent_id=parent_id, listeners=listeners, team=team, trigger=trigger)
    if seed_from and Path(seed_from).is_dir() and not workspace:
        shutil.copytree(seed_from, state.workspace, dirs_exist_ok=True, ignore=COPY_IGNORE)
    state.log("run_started", task=task, title=state.title, options=config.to_options(),
              workspace=str(state.workspace), repo=repo, branch=branch, parent_id=parent_id,
              auth_mode=state.auth_mode, team_id=(team or {}).get("id"), team_name=(team or {}).get("name"),
              trigger=trigger)
    return state


def classify_error(message: str) -> tuple[str, str]:
    """(kind, hint) for a crash message."""
    m = (message or "").lower()
    if any(k in m for k in ("not logged in", "login", "401", "invalid api key", "authentication", "unauthorized")):
        return "auth", "Your Claude login expired. Run `claude` in a terminal, then `/login`, and start the run again."
    if any(k in m for k in ("usage limit", "rate limit", "429", "rate_limit", "limit reached")):
        return "limit", "You've hit your plan's usage limit. Wait for it to reset, then continue the run."
    return "crash", "The run crashed. Check the technical details and try again."


async def execute_run(state: RunState, *, runner=default_runner, catalog: Catalog | None = None,
                      client_factory=ClaudeSDKClient, interactive: bool = False, notify=None) -> RunState:
    """Run the orchestrator to the end. Never raises: stop and crashes are logged and saved."""
    config = state.config
    catalog = catalog or load_catalog()
    state.approvals = ApprovalBroker(state, interactive=interactive, notify=notify)
    tools = OrchestraTools(state, runner=runner, catalog=catalog)
    state.tools = tools
    task = state.task
    if state.team:  # a saved team: its members exist before the orchestrator starts
        for m in state.team.get("members", []):
            await tools.create_agent({**m, "tier_reason": m.get("tier_reason") or "team member"})
        task = f"{prompts.team_context(state.team)}\n{task}"
    if state.repo:
        task = (f"{task}\n\nYou are working in an EXISTING codebase at the workspace root. "
                "Have an agent explore its structure, conventions and tests before changing anything.")

    options = ClaudeAgentOptions(
        system_prompt=prompts.orchestrator_prompt(
            catalog.prompt_lines(config), config.budget, summary_lines(tools.playbooks),
            config.playbook if config.playbook in tools.playbooks else ""),
        model=config.orchestrator_model,
        cwd=str(state.workspace),
        mcp_servers={SERVER_NAME: tools.mcp_server()},
        tools=[],                       # no built-in tools: it can only orchestrate
        allowed_tools=MCP_TOOL_NAMES,
        permission_mode="dontAsk",
        max_turns=config.budget.max_orchestrator_turns,
        setting_sources=[],
        env=dict(DISABLE_ENV),          # your claude.ai connectors are for workers that were given them
    )

    try:
        async with client_factory(options=options) as client:
            prompt = f"User task:\n{task}\n\nStart by planning, then create your agents."
            orch_cost = 0.0
            for round_no in range(config.budget.max_nudges + 1):
                await client.query(prompt)
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock) and block.text.strip():
                                state.log("orchestrator_said", text=block.text.strip())
                    elif isinstance(msg, ResultMessage):
                        # cost on a long-lived session is a running total, so add only the change
                        total = msg.total_cost_usd or 0.0
                        state.record_usage(msg.num_turns, max(total - orch_cost, 0.0), role="orchestrator",
                                           model=config.orchestrator_model)
                        orch_cost = max(orch_cost, total)
                        if msg.is_error and msg.errors:
                            raise RuntimeError("; ".join(msg.errors))

                # ---- the "keep looping until it's really done" check ----
                if state.final_result is not None:
                    break
                if problem := state.budget_problem():
                    state.log("budget_exhausted", reason=problem)
                    prompt = (
                        f"Budget exhausted: {problem}. Call finish now with give_up=true, "
                        "summarizing what is done and what is not."
                    )
                    if round_no == config.budget.max_nudges:
                        break
                    continue
                pending = [f"{t.task_id} ({t.status})" for t in state.unfinished()]
                state.log("nudge", round=round_no + 1, pending=pending)
                prompt = (
                    "You stopped without calling finish. "
                    + (f"Unfinished tasks: {pending}. " if pending else "")
                    + "Check view_board, fix what failed, and continue until finish is accepted."
                    + (prompts.user_messages(state.take_messages()) if state.inbox else "")
                )

        if state.final_result is None:
            state.final_result = "Run ended without an accepted finish. See board.json and log.jsonl."
            state.pending_finish = {"give_up": True, "result": state.final_result, "tasks": len(state.board)}
        state.log("finished", **state.pending_finish)
    except asyncio.CancelledError:
        state.approvals.expire_all()
        state.log("run_stopped")
        _save(state)
        raise
    except Exception as e:  # CLI crash, auth problem, plan limit...
        state.approvals.expire_all()
        kind, hint = classify_error(str(e))
        state.error = {"error": f"{type(e).__name__}: {e}", "kind": kind, "hint": hint}
        state.log("run_failed", **state.error)
    _save(state)
    return state


def _save(state: RunState) -> None:
    (state.run_dir / "final.md").write_text(state.final_result or "")
    state.save_board()


async def run(task: str, config: Config, runs_dir: Path = Path("runs"), workspace: Path | None = None, *,
              branch: str | None = None, listeners=None, runner=default_runner, catalog: Catalog | None = None,
              connectors: bool = True) -> RunState:
    """Create and execute a run in one go (CLI). Your claude.ai connectors join the catalog."""
    state = create_run(task, config, runs_dir, workspace, repo=str(workspace) if workspace else None,
                       branch=branch, listeners=listeners)
    if catalog is None:
        catalog = with_connectors(load_catalog(), discover_connectors()) if connectors else load_catalog()
    try:
        return await execute_run(state, runner=runner, catalog=catalog)
    except asyncio.CancelledError:
        return state


# ---- continue and follow-up -------------------------------------------------

def _read_parent(parent_dir: Path) -> tuple[dict, dict, str]:
    meta = json.loads((parent_dir / "meta.json").read_text()) if (parent_dir / "meta.json").exists() else {}
    board = json.loads((parent_dir / "board.json").read_text()) if (parent_dir / "board.json").exists() else {}
    final = (parent_dir / "final.md").read_text() if (parent_dir / "final.md").exists() else ""
    return meta, board, final


def continue_task(parent_dir: Path) -> str:
    """Task text for a run that picks up where the parent stopped."""
    meta, board, final = _read_parent(Path(parent_dir))
    tasks = board.get("board", {}).values()
    done = [f"- {t.get('title') or t['task_id']}: done" for t in tasks if t.get("status") in ("done", "replaced")]
    todo = [f"- {t.get('title') or t['task_id']} ({t.get('status')}): {t.get('task', '')}\n  done when: "
            f"{t.get('done_when', '')}\n  last feedback: {t.get('feedback', '')[:400]}"
            for t in tasks if t.get("status") not in ("done", "replaced")]
    return (f"{meta.get('task', '')}\n\n## Continue an earlier run\n"
            "The workspace already contains the earlier run's files. Do not redo finished work.\n"
            "Finished:\n" + ("\n".join(done) or "- nothing") + "\n\nUnfinished (finish these):\n"
            + ("\n".join(todo) or "- nothing listed; check the workspace against the original task")
            + (f"\n\nEarlier summary:\n{final[:2000]}" if final else ""))


def follow_up_task(parent_dir: Path, new_task: str) -> str:
    meta, _, final = _read_parent(Path(parent_dir))
    return (f"{new_task}\n\n## Context from the earlier run\nOriginal task: {meta.get('task', '')}\n"
            "The workspace contains its files." + (f"\nIts summary:\n{final[:2000]}" if final else ""))
