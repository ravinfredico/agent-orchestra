"""User approval for outward tool calls (send email, create event, post...).

The SDK calls `can_use_tool` before each gated tool call. Non-outward tools pass straight through.
Outward ones log `approval_requested`, wait for the user's decision, then log `approval_resolved`.
In CLI mode (no server to answer) outward calls are denied with a clear message.
"""

import asyncio
import json
import secrets
from typing import Callable

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

SECRET_KEYS = ("token", "password", "secret", "authorization", "api_key", "apikey")
DENIED = "Denied by the user. Continue without this action."
NO_UI = "This action needs the user's approval, which is only available in the web app. Continue without it."


def preview(tool_input: dict, limit: int = 600) -> str:
    """Short, redacted, readable version of a tool call's input."""
    def redact(v):
        if isinstance(v, dict):
            return {k: ("•••" if any(s in k.lower() for s in SECRET_KEYS) else redact(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [redact(x) for x in v]
        return v
    text = json.dumps(redact(tool_input or {}), ensure_ascii=False, indent=1)
    return text if len(text) <= limit else text[:limit] + "…"


class ApprovalBroker:
    def __init__(self, state, interactive: bool = False, notify: Callable[[dict], None] | None = None):
        self.state = state
        self.interactive = interactive
        self.notify = notify
        self.pending: dict[str, asyncio.Future] = {}

    async def request(self, *, agent: str, task_id: str, tool: str, catalog_id: str, tool_input: dict) -> bool:
        approval_id = "ap_" + secrets.token_hex(4)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self.pending[approval_id] = fut
        event = self.state.log("approval_requested", approval_id=approval_id, task_id=task_id, agent=agent,
                               tool=tool, catalog_id=catalog_id, preview=preview(tool_input))
        if self.notify:
            try:
                self.notify(event)
            except Exception:
                pass
        try:
            decision = await fut
        finally:
            self.pending.pop(approval_id, None)
        self.state.log("approval_resolved", approval_id=approval_id, decision=decision)
        return decision == "approved"

    def resolve(self, approval_id: str, approve: bool) -> bool:
        fut = self.pending.get(approval_id)
        if not fut or fut.done():
            return False
        fut.set_result("approved" if approve else "denied")
        return True

    def expire_all(self) -> None:
        for fut in list(self.pending.values()):
            if not fut.done():
                fut.set_result("expired")


def make_can_use_tool(broker: ApprovalBroker | None, toolset, agent: str, task_id: str):
    """Build the SDK `can_use_tool` callback for one agent attempt."""

    async def can_use_tool(tool_name: str, tool_input: dict, context) -> PermissionResultAllow | PermissionResultDeny:
        if not toolset.is_outward(tool_name):
            return PermissionResultAllow(updated_input=tool_input)
        if broker is None or not broker.interactive:
            return PermissionResultDeny(message=NO_UI)
        ok = await broker.request(agent=agent, task_id=task_id, tool=tool_name,
                                  catalog_id=toolset.catalog_id_for(tool_name), tool_input=tool_input)
        if ok:
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message=DENIED)

    return can_use_tool
