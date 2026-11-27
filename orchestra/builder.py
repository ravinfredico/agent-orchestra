"""Team builder (M9): one message ("I want a marketing team") becomes a proposed team.

One model call, no tools, structured output. The proposal is never saved here: you review it, edit it
in the team editor and save it like any team.

Rules (PRD F22, F23, F31):
- Members only get tools that are in the catalog (built-ins, MCP entries, plugins, your claude.ai
  connectors). Anything else the model asks for goes into the member's `wants` and becomes a setup
  step ("Connect Gmail at claude.ai"). Nothing is ever invented or added to the catalog.
- Which actions ask you first is worked out from the catalog, not from the model.
- A member skips a tool until it is set up. Once you connect it, the member gets it at the next run.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .config import TIERS
from .connectors import DISABLE_ENV

BUILDER_MODEL = "sonnet"   # one call per proposal; haiku tends to miss approvals and schedules
MAX_MEMBERS = 8

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Short team name, 1 to 3 words"},
        "goal": {"type": "string", "description": "One sentence: what the team is for and its limits"},
        "summary": {"type": "string", "description": "One or two plain sentences to the user about the team"},
        "members": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string", "description": "lowercase one word, e.g. copywriter"},
            "role": {"type": "string", "description": "What this member does, one line"},
            "system_prompt": {"type": "string"},
            "tools": {"type": "array", "items": {"type": "string"},
                      "description": "Catalog ids. For a service not in the catalog, use connector.<service>"},
            "tier": {"type": "string", "enum": list(TIERS)},
        }, "required": ["name", "role", "tools", "tier"]}},
        "schedule": {"type": "array", "items": {"type": "object", "properties": {
            "cron": {"type": "string"}, "task": {"type": "string"}}, "required": ["cron", "task"]}},
        "outputs": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["question", "options"]}},
    },
    "required": ["name", "goal", "summary", "members", "schedule", "outputs", "questions"],
}

PROMPT = """You design small teams of AI agents for ChaCha PA. The user describes a goal in one message.
Propose a team that reaches it with as little model usage as possible.

Rules:
- 2 to 5 members. Each has one clear job. Names are lowercase single words.
- Tiers: haiku for search, reading, summaries, posting and simple edits; sonnet for writing, design
  and planning; opus never in a proposal.
- Tools: only ids from the catalog below. Give each member only what its job needs. Prefer the
  user's connectors (connector.*) for services: they work in the user's real Notion, Slack, Figma...
- If the team needs a service that is not in the catalog, still give it to the member as
  connector.<service> (e.g. connector.gmail). The app turns it into a setup step. Never pretend a
  missing tool exists in any other way.
- Schedule: 0 to 3 cron slots ("minute hour day month weekday"), each with a concrete task. Only when
  the goal implies regular work.
- Outputs: 2 to 5 concrete things the team produces (files, drafts, posts).
- Questions: at most 2, only for facts you cannot guess (which channel, which stocks), each with 2 to
  4 short options.
- Anything that moves money stays out. Stocks or finance teams never trade.
- Each system_prompt: 2 to 4 sentences, the member's job and its quality bar.

Catalog:
{catalog}
"""


def catalog_lines(entries) -> str:
    out = []
    for e in entries:
        if not e.enabled:
            continue
        note = f" (not set up: {e.unavailable})" if e.unavailable else ""
        out.append(f"- {e.id}: {e.description}{note}")
    return "\n".join(out)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _label(tool_id: str, catalog) -> str:
    e = catalog.by_id.get(tool_id)
    if e is not None and e.connector:
        return e.connector.split(" ", 1)[-1]
    if tool_id.startswith("connector."):
        return tool_id.split(".", 1)[1].replace("-", " ").title()
    return tool_id


def clean_proposal(raw: dict, catalog) -> dict:
    """Turn the model's answer into a team the editor can load, plus review notes.

    Tools not in the catalog move to the member's `wants`. Raises ValueError when there is no team.
    """
    from server.teams import parse_cron   # the server owns cron; imported late to keep engine imports light

    if not isinstance(raw, dict):
        raise ValueError("the answer was not a team")
    known = {e.id for e in catalog.entries if e.enabled}
    members, seen = [], set()
    for m in (raw.get("members") or [])[:MAX_MEMBERS]:
        if not isinstance(m, dict):
            continue
        name = re.sub(r"[^a-z0-9_-]", "_", str(m.get("name", "")).strip().lower())[:30]
        if not name or name in seen:
            continue
        seen.add(name)
        tools, wants = [], []
        for t in m.get("tools") or []:
            t = str(t).strip()
            if t in known:
                tools.append(t)
            elif t:
                # "Gmail" and "connector.Gmail" both mean the Gmail connector; other dotted ids stay as they are
                if t.lower().startswith("connector."):
                    cid = "connector." + _slug(t[len("connector."):])
                elif "." in t:
                    cid = t
                else:
                    cid = "connector." + _slug(t)
                (tools if cid in known else wants).append(cid)
        tier = m.get("tier") if m.get("tier") in TIERS else "sonnet"
        if tier == "opus":
            tier = "sonnet"
        members.append({"name": name, "role": str(m.get("role", ""))[:200],
                        "system_prompt": str(m.get("system_prompt", "") or f"You are the team's {name}.")[:8000],
                        "tools": list(dict.fromkeys(tools)), "wants": list(dict.fromkeys(wants)), "tier": tier})
    if not members:
        raise ValueError("the answer had no members")
    schedule = []
    for s in (raw.get("schedule") or [])[:3]:
        try:
            cron, task = str(s.get("cron", "")).strip(), str(s.get("task", "")).strip()
            parse_cron(cron)
        except (ValueError, AttributeError):
            continue   # a bad time is dropped, not guessed
        if task:
            schedule.append({"cron": cron, "task": task[:4000]})
    questions = []
    for q in (raw.get("questions") or [])[:2]:
        if isinstance(q, dict) and str(q.get("question", "")).strip():
            questions.append({"question": str(q["question"]).strip()[:200],
                              "options": [str(o)[:60] for o in (q.get("options") or [])[:4] if str(o).strip()]})
    team = {"name": str(raw.get("name", "")).strip()[:60] or "New team",
            "goal": str(raw.get("goal", "")).strip()[:2000], "members": members, "schedule": schedule,
            "outputs": [str(o)[:200] for o in (raw.get("outputs") or [])[:8] if str(o).strip()],
            "timezone": "", "enabled": True, "hook": {"enabled": False, "task": ""}}
    return {"team": team, "summary": str(raw.get("summary", "")).strip()[:600], "questions": questions,
            **review(team, catalog)}


def review(team: dict, catalog) -> dict:
    """What a team needs from you: approvals (from the catalog) and setup steps. No model call."""
    approvals, setup, seen = [], [], set()
    for m in team.get("members", []):
        for t in m.get("tools", []):
            e = catalog.by_id.get(t)
            if e is None:
                continue
            label = _label(t, catalog)
            if e.kind == "connector" or e.outward_tools:
                approvals.append(f"{m['name']} asks before it sends, posts or changes anything in {label}")
            if e.unavailable and t not in seen:
                seen.add(t)
                setup.append({"kind": "sign_in", "tool": t, "service": label, "text": e.unavailable[0].upper() + e.unavailable[1:]})
            elif e.requires == "allow_bash" and t not in seen:
                seen.add(t)
                setup.append({"kind": "option", "tool": t, "service": "Shell",
                              "text": "Turn on Shell in the team's run options (it stays sandboxed)"})
        for t in m.get("wants", []):
            if t in seen:
                continue
            seen.add(t)
            label = _label(t, catalog)
            if t.startswith("connector."):
                setup.append({"kind": "connect", "tool": t, "service": label,
                              "text": f"Connect {label} at claude.ai, Settings, Connectors. It shows up here within 5 minutes"})
            else:
                setup.append({"kind": "missing_tool", "tool": t, "service": label,
                              "text": f"{label} is not in the tool catalog yet. Add it to tools.catalog.json or plugins/"})
    return {"approvals": approvals, "setup": setup}


async def propose(goal: str, catalog, runner=None, model: str = BUILDER_MODEL) -> dict:
    """One model call. Raises ValueError with a plain reason when it can't produce a team."""
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("Describe the team first")
    if runner is None:
        from .runner import run_agent as runner
    with tempfile.TemporaryDirectory() as tmp:
        res = await runner(prompt=f"The user wants: {goal[:2000]}", system_prompt=PROMPT.format(catalog=catalog_lines(catalog.entries)),
                           tools=[], model=model, cwd=Path(tmp), max_turns=3, output_schema=SCHEMA, env=DISABLE_ENV)
    if res.is_error:
        raise ValueError(f"the model call failed ({res.error or 'no answer'})")
    raw = res.structured
    if not isinstance(raw, dict):
        import json
        m = re.search(r"\{.*\}", res.text or "", re.S)
        try:
            raw = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            raw = None
    out = clean_proposal(raw, catalog)
    out["cost_usd"] = res.cost_usd or 0.0
    return out
