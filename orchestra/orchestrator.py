"""The outer loop: run the orchestrator until it calls finish or the budget runs out."""

import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from . import prompts
from .config import Config
from .state import RunState
from .tools import MCP_TOOL_NAMES, SERVER_NAME, OrchestraTools


async def run(task: str, config: Config, runs_dir: Path = Path("runs"),
              workspace: Path | None = None) -> RunState:
    run_dir = runs_dir / time.strftime("%Y%m%d-%H%M%S")
    state = RunState(task, config, run_dir, workspace)
    tools = OrchestraTools(state)
    state.log("start", task=task, run_dir=str(run_dir), workspace=str(state.workspace))
    if workspace:
        task = (f"{task}\n\nYou are working in an EXISTING codebase at the workspace root. "
                "Have an agent explore its structure, conventions and tests before changing anything.")

    options = ClaudeAgentOptions(
        system_prompt=prompts.orchestrator_prompt(config.tool_registry(), config.budget),
        model=config.orchestrator_model,
        cwd=str(state.workspace),
        mcp_servers={SERVER_NAME: tools.mcp_server()},
        tools=[],                       # no built-in tools: it can only orchestrate
        allowed_tools=MCP_TOOL_NAMES,
        permission_mode="dontAsk",
        max_turns=config.budget.max_orchestrator_turns,
        setting_sources=[],
    )

    async with ClaudeSDKClient(options=options) as client:
        prompt = f"User task:\n{task}\n\nStart by planning, then create your agents."
        orch_cost = 0.0
        for round_no in range(config.budget.max_nudges + 1):
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            state.log("orchestrator", say=block.text.strip())
                elif isinstance(msg, ResultMessage):
                    # cost on a long-lived session is a running total, so add only the change
                    total = msg.total_cost_usd or 0.0
                    state.record_usage(msg.num_turns, max(total - orch_cost, 0.0))
                    orch_cost = max(orch_cost, total)

            # ---- the "keep looping until it's really done" check ----
            if state.final_result is not None:
                break
            if problem := state.budget_problem():
                state.log("budget", reason=problem)
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
            )

    if state.final_result is None:
        state.final_result = "Run ended without an accepted finish. See board.json and log.jsonl."
    (run_dir / "final.md").write_text(state.final_result)
    state.save_board()
    return state
