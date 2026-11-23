"""Run a single agent (worker or checker) to completion with the Claude Agent SDK."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
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
    allowed_tools: list[str] | None = None,
    mcp_servers: dict | None = None,
    plugins: list[dict] | None = None,
    can_use_tool: Callable | None = None,
    sandbox: dict | None = None,
    add_dirs: list[str] | None = None,
    on_tool_use: Callable[[str, dict], None] | None = None,
) -> AgentResult:
    """Run one agent loop until it stops, hits max_turns, or errors.

    tools          the built-in tools this agent can see
    allowed_tools  what runs without asking (defaults to `tools`); MCP servers as "mcp__<name>"
    can_use_tool   approval callback for gated (outward) MCP tools
    on_tool_use    called with (tool_name, input) for every tool call, for live activity
    output_schema  optional JSON schema, the final answer comes back in .structured
    """
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        cwd=str(cwd),
        tools=tools,                                      # what exists for this agent
        allowed_tools=allowed_tools if allowed_tools is not None else tools,  # runs without asking
        # dontAsk: anything not allowed is denied. default: the approval callback is asked instead.
        permission_mode="default" if can_use_tool else "dontAsk",
        max_turns=max_turns,
        setting_sources=[],                               # ignore local Claude Code settings/CLAUDE.md
    )
    if mcp_servers:
        options.mcp_servers = mcp_servers
    if plugins:
        options.plugins = plugins
    if can_use_tool:
        options.can_use_tool = can_use_tool
    if sandbox:
        options.sandbox = sandbox
    if add_dirs:
        options.add_dirs = add_dirs
    if output_schema:
        options.output_format = {"type": "json_schema", "schema": output_schema}

    texts: list[str] = []
    result: ResultMessage | None = None
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        texts.append(b.text)
                    elif isinstance(b, ToolUseBlock) and on_tool_use:
                        try:
                            on_tool_use(b.name, b.input or {})
                        except Exception:
                            pass
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
