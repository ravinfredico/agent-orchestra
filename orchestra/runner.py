"""Run a single agent (worker or checker) to completion with the Claude Agent SDK."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)


@dataclass
class AgentResult:
    text: str
    structured: Any = None
    turns: int = 0
    cost_usd: float | None = None
    is_error: bool = False
    error: str = ""


async def run_agent(
    *,
    prompt: str,
    system_prompt: str,
    tools: list[str],
    model: str,
    cwd: Path,
    max_turns: int,
    output_schema: dict | None = None,
) -> AgentResult:
    """Run one agent loop until it stops, hits max_turns, or errors.

    tools          the only built-in tools this agent can see
    output_schema  optional JSON schema, the final answer comes back in .structured
    """
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        cwd=str(cwd),
        tools=tools,                 # what exists for this agent
        allowed_tools=tools,         # what runs without asking
        permission_mode="dontAsk",   # anything else is denied, never prompts
        max_turns=max_turns,
        setting_sources=[],          # ignore your local Claude Code settings/CLAUDE.md
    )
    if output_schema:
        options.output_format = {"type": "json_schema", "schema": output_schema}

    texts: list[str] = []
    result: ResultMessage | None = None
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                texts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
            elif isinstance(msg, ResultMessage):
                result = msg
    except Exception as e:  # CLI crash, auth problem, rate limit, etc.
        return AgentResult(text="\n".join(texts), is_error=True, error=f"{type(e).__name__}: {e}")

    if result is None:
        return AgentResult(text="\n".join(texts), is_error=True, error="no result message")

    return AgentResult(
        text=result.result or "\n".join(texts),
        structured=result.structured_output,
        turns=result.num_turns,
        cost_usd=result.total_cost_usd,
        is_error=result.is_error,
        error=("; ".join(result.errors) if result.errors else result.subtype) if result.is_error else "",
    )
