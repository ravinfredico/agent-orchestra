"""Saved teams (M8): members, memory, schedule, a data webhook, and the room.

A team lives in `teams/<id>/`:
  team.json    name, goal, members, schedule, timezone, hook, options, enabled
  memory.md    notes you write, plus a "Past runs" list the app appends after each run
  events.jsonl team-level events (skipped triggers), shown in the room

A team never runs on its own. A trigger starts a normal verified run linked to it: a schedule slot,
your message in the room, or a POST to its webhook. Between triggers it costs nothing.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orchestra.config import TIERS, Config
from orchestra.state import read_events

MEMORY_MAX = 8000          # chars kept in memory.md; the oldest past runs drop off first
PAST_HEADER = "## Past runs"
ROOM_KINDS = {"run_started", "user_message", "orchestrator_said", "task_assigned", "task_passed",
              "task_failed", "approval_requested", "approval_resolved", "finished", "run_failed", "run_stopped",
              "run_interrupted"}


class TeamError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ---- cron: "min hour day month weekday", with *, lists, ranges and steps --------------

_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _field(spec: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/", 1)
            step = int(st)
            if step < 1:
                raise ValueError("step must be 1 or more")
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
        if a < lo or b > hi or a > b:
            raise ValueError(f"{part} is outside {lo}-{hi}")
        out.update(range(a, b + 1, step))
    return out


def parse_cron(expr: str) -> list[set[int]]:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("a schedule needs 5 fields: minute hour day month weekday")
    fields = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES)]
    fields[4] = {d % 7 for d in fields[4]}  # 7 also means Sunday
    return fields


def cron_matches(expr: str, when: datetime) -> bool:
    """Weekday 0 is Sunday, as in cron. Day and weekday must both match (no cron OR rule)."""
    m, h, dom, mon, dow = parse_cron(expr)
    return (when.minute in m and when.hour in h and when.day in dom and when.month in mon
            and (when.isoweekday() % 7) in dow)


def team_now(team: dict, now: float | None = None) -> datetime:
    tz = None
    if team.get("timezone"):
        try:
            tz = ZoneInfo(team["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            tz = None
    ts = time.time() if now is None else now
    return datetime.fromtimestamp(ts, tz) if tz else datetime.fromtimestamp(ts).astimezone()


# ---- store ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30]
    return s or "team"


class TeamStore:
    def __init__(self, root: Path = Path("teams")):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, team_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]{1,40}", team_id or ""):
            raise TeamError(404, "Team not found")
        d = self.root / team_id
        if not (d / "team.json").exists():
            raise TeamError(404, "Team not found")
        return d

    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir()):
            if (d / "team.json").exists():
                out.append(json.loads((d / "team.json").read_text()))
        return out

    def get(self, team_id: str) -> dict:
        d = self._dir(team_id)
        team = json.loads((d / "team.json").read_text())
        team["memory"] = (d / "memory.md").read_text() if (d / "memory.md").exists() else ""
        return team

    def create(self, data: dict, catalog_ids: list[str]) -> dict:
        team = clean_team(data, catalog_ids)
        base = _slug(team["name"])
        team_id = base
        while (self.root / team_id).exists():
            team_id = f"{base}-{secrets.token_hex(2)}"
        team.update(id=team_id, created_at=round(time.time(), 2),
                    hook={**team["hook"], "secret": secrets.token_urlsafe(18)})
        d = self.root / team_id
        d.mkdir(parents=True)
        memory = str(data.get("memory") or "").strip() or f"## Notes\n\n{PAST_HEADER}\n"
        (d / "memory.md").write_text(memory[:MEMORY_MAX])
        self._write(team)
        return self.get(team_id)

    def update(self, team_id: str, data: dict, catalog_ids: list[str]) -> dict:
        old = self.get(team_id)
        team = clean_team({**old, **data}, catalog_ids)
        team.update(id=team_id, created_at=old.get("created_at"),
                    hook={**team["hook"], "secret": old.get("hook", {}).get("secret") or secrets.token_urlsafe(18)})
        if "memory" in data:
            (self.root / team_id / "memory.md").write_text(str(data["memory"] or "")[:MEMORY_MAX])
        self._write(team)
        return self.get(team_id)

    def delete(self, team_id: str) -> None:
        d = self._dir(team_id)
        for p in sorted(d.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        d.rmdir()

    def _write(self, team: dict) -> None:
        team = {k: v for k, v in team.items() if k != "memory"}
        (self.root / team["id"] / "team.json").write_text(json.dumps(team, indent=2))

    # ---- memory and team events ------------------------------------------------------

    def remember_run(self, team_id: str, title: str, result: str, status: str, when: float | None = None) -> None:
        """Append one line per finished run under "Past runs", dropping the oldest when too long."""
        d = self._dir(team_id)
        path = d / "memory.md"
        text = path.read_text() if path.exists() else ""
        if PAST_HEADER not in text:
            text = text.rstrip() + f"\n\n{PAST_HEADER}\n"
        day = time.strftime("%Y-%m-%d", time.localtime(when or time.time()))
        summary = " ".join((result or "").split())[:300]
        line = f"- {day} · {title} · {status}: {summary}"
        head, past = text.split(PAST_HEADER, 1)
        lines = [ln for ln in past.strip().splitlines() if ln.strip()] + [line]
        while len(head) + len(PAST_HEADER) + sum(len(ln) + 1 for ln in lines) > MEMORY_MAX and len(lines) > 1:
            lines.pop(0)
        path.write_text(f"{head.rstrip()}\n\n{PAST_HEADER}\n" + "\n".join(lines) + "\n")

    def log(self, team_id: str, kind: str, **data) -> dict:
        e = {"t": round(time.time(), 3), "type": kind, **data}
        with (self._dir(team_id) / "events.jsonl").open("a") as f:
            f.write(json.dumps(e) + "\n")
        return e

    def events(self, team_id: str) -> list[dict]:
        p = self._dir(team_id) / "events.jsonl"
        if not p.exists():
            return []
        return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def clean_team(data: dict, catalog_ids: list[str]) -> dict:
    """Validate and normalise a team from the API. Raises TeamError(400) with a plain reason."""
    name = str(data.get("name", "")).strip()[:60]
    if not name:
        raise TeamError(400, "A team needs a name")
    members = []
    seen = set()
    for m in data.get("members") or []:
        mname = re.sub(r"[^a-zA-Z0-9_-]", "_", str(m.get("name", "")).strip())
        if not mname:
            raise TeamError(400, "Every member needs a name")
        if mname in seen:
            raise TeamError(400, f"Two members are called {mname}")
        seen.add(mname)
        tools = list(dict.fromkeys(m.get("tools") or []))
        unknown = [t for t in tools if t not in catalog_ids]
        if unknown:
            raise TeamError(400, f"{mname}: unknown tools {unknown}. Pick from the catalog: {catalog_ids}")
        tier = m.get("tier") or "sonnet"
        if tier not in TIERS:
            raise TeamError(400, f"{mname}: tier must be one of {TIERS}")
        # wants: tools the team builder asked for that aren't in the catalog yet (setup steps)
        wants = [str(w)[:80] for w in dict.fromkeys(m.get("wants") or []) if str(w).strip() and w not in tools][:10]
        members.append({"name": mname, "role": str(m.get("role", ""))[:200],
                        "system_prompt": str(m.get("system_prompt", "") or f"You are the team's {mname}.")[:8000],
                        "tools": tools, "wants": wants, "tier": tier})
    schedule = []
    for slot in data.get("schedule") or []:
        cron, task = str(slot.get("cron", "")).strip(), str(slot.get("task", "")).strip()
        if not cron or not task:
            raise TeamError(400, "Each schedule slot needs a time (cron) and a task")
        try:
            parse_cron(cron)
        except ValueError as e:
            raise TeamError(400, f"Schedule '{cron}': {e}")
        schedule.append({"cron": cron, "task": task[:4000]})
    tz = str(data.get("timezone") or "").strip()
    if tz:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise TeamError(400, f"Unknown time zone '{tz}'. Use a name like Asia/Jakarta, or leave it empty for this machine's.")
    hook = data.get("hook") or {}
    options = Config.from_options(data.get("options") or {}).to_options()
    outputs = [str(o).strip()[:200] for o in (data.get("outputs") or []) if str(o).strip()][:8]
    return {"name": name, "goal": str(data.get("goal", "")).strip()[:2000], "members": members, "outputs": outputs,
            "schedule": schedule, "timezone": tz, "enabled": bool(data.get("enabled", True)),
            "hook": {"enabled": bool(hook.get("enabled", False)), "task": str(hook.get("task", "")).strip()[:4000]},
            "options": options}




def due_slots(team: dict, now: float | None = None) -> list[tuple[int, str]]:
    """Schedule slots that match this minute in the team's time zone: [(index, minute key)]."""
    if not team.get("enabled", True):
        return []
    when = team_now(team, now)
    key = when.strftime("%Y-%m-%dT%H:%M")
    return [(i, key) for i, slot in enumerate(team.get("schedule", [])) if cron_matches(slot["cron"], when)]


def room_items(team_events: list[dict], run_dirs: list[Path], limit: int = 200) -> list[dict]:
    """The room: your messages, the team's talk and hand-offs, from team runs' logs and team events."""
    items: list[dict] = []
    for e in team_events:
        if e["type"] == "trigger_skipped":
            items.append({"t": e["t"], "kind": "system", "text": f"Skipped {e.get('what', 'a trigger')}: {e.get('why', '')}"})
    for d in run_dirs:
        run_id = Path(d).name
        titles: dict[str, str] = {}
        asked: dict[str, str] = {}   # approval id -> what was asked
        for e in read_events(d):
            if e["type"] not in ROOM_KINDS:
                continue
            base = {"t": e["t"], "run_id": run_id, "seq": e["seq"]}
            t = e["type"]
            if t == "run_started":
                trig = e.get("trigger") or {}
                kind = trig.get("kind", "manual")
                if kind == "message":
                    items.append({**base, "kind": "you", "text": e.get("task", "")})
                else:
                    label = {"schedule": "Scheduled run", "webhook": "New data"}.get(kind, "Run started")
                    items.append({**base, "kind": "system", "text": f"{label}: {e.get('title', '')}"})
            elif t == "user_message":
                items.append({**base, "kind": "you", "text": e.get("text", "")})
            elif t == "orchestrator_said":
                items.append({**base, "kind": "agent", "from": "orchestrator", "text": e.get("text", "")})
            elif t == "task_assigned":
                titles[e["task_id"]] = e.get("title", e["task_id"])
                items.append({**base, "kind": "handoff", "from": "orchestrator", "to": e.get("agent", ""),
                              "text": e.get("title", ""), "task_id": e["task_id"]})
            elif t == "task_passed":
                items.append({**base, "kind": "result", "from": "checker", "passed": True,
                              "text": f"{titles.get(e['task_id'], e['task_id'])} passed: {e.get('short', '')}"})
            elif t == "task_failed":
                items.append({**base, "kind": "result", "from": "checker", "passed": False,
                              "text": f"{titles.get(e['task_id'], e['task_id'])} failed"})
            elif t == "approval_requested":
                asked[e.get("approval_id")] = str(e.get("tool", "")).split("__")[-1].replace("_", " ")
                items.append({**base, "kind": "approval", "from": e.get("agent", ""), "approval_id": e.get("approval_id"),
                              "text": f"wants to {str(e.get('tool', '')).split('__')[-1].replace('_', ' ')}. Approve it in the run."})
            elif t == "approval_resolved":
                word = {"approved": "Approved", "denied": "Denied"}.get(e.get("decision"), "Not answered")
                items.append({**base, "kind": "system", "approval_id": e.get("approval_id"),
                              "text": f"{word}: {asked.get(e.get('approval_id'), 'an action')}"})
            elif t == "finished":
                items.append({**base, "kind": "agent", "from": "orchestrator", "final": True,
                              "text": e.get("result", "")})
            else:
                items.append({**base, "kind": "system", "text": {"run_failed": "The run crashed",
                              "run_stopped": "Stopped", "run_interrupted": "Interrupted"}[t]})
    items.sort(key=lambda i: (i["t"], i.get("seq", 0)))
    return items[-limit:]


# ---- triggers: the only way a team spends usage -----------------------------------------

class TeamRunner:
    """Starts team runs from triggers and keeps memory up to date. One run per team at a time."""

    def __init__(self, store: "TeamStore", manager, catalog_ids):
        self.store = store
        self.manager = manager
        self.catalog_ids = catalog_ids        # callable -> list of catalog ids
        self.fired: dict[tuple[str, int], str] = {}   # (team, slot) -> minute key already fired
        manager.on_end = self.on_run_end

    def active_run(self, team_id: str) -> str | None:
        for rid, h in self.manager.active.items():
            if (h.state.team or {}).get("id") == team_id:
                return rid
        return None

    def run_dirs(self, team_id: str, limit: int = 20) -> list[Path]:
        out = []
        for d in sorted(self.manager.runs_dir.iterdir(), reverse=True):
            meta = d / "meta.json"
            if meta.exists():
                try:
                    if json.loads(meta.read_text()).get("team_id") == team_id:
                        out.append(d)
                except json.JSONDecodeError:
                    continue
            if len(out) >= limit:
                break
        return list(reversed(out))

    async def start(self, team_id: str, task: str, trigger: dict) -> dict:
        """Start a team run, or pass the message to the running one. Returns {run_id, steered}."""
        team = self.store.get(team_id)
        busy = self.active_run(team_id)
        if busy:
            if trigger["kind"] == "schedule":
                self.store.log(team_id, "trigger_skipped", what=f"the {trigger.get('at', '')} run",
                               why="the team was still busy")
                raise TeamError(409, "The team is busy")
            self.manager.steer(busy, task)
            return {"run_id": busy, "steered": True}
        run_team = {"id": team["id"], "name": team["name"], "goal": team.get("goal", ""),
                    "members": team.get("members", []), "memory": team.get("memory", "")}
        run_id = await self.manager.start(task, dict(team.get("options") or {}), team=run_team, trigger=trigger)
        return {"run_id": run_id, "steered": False}

    async def message(self, team_id: str, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise TeamError(400, "Message is empty")
        return await self.start(team_id, text, {"kind": "message"})

    async def webhook(self, team_id: str, secret: str, body: str) -> dict:
        team = self.store.get(team_id)
        hook = team.get("hook") or {}
        import hmac
        if not hook.get("enabled") or not hook.get("secret") or not hmac.compare_digest(secret, hook["secret"]):
            raise TeamError(404, "Not found")
        task = f"{hook.get('task') or 'New data arrived. Decide what to do with it.'}\n\nNew data:\n```\n{body[:4000]}\n```"
        return await self.start(team_id, task, {"kind": "webhook"})

    async def tick(self, now: float | None = None) -> list[str]:
        """Fire every schedule slot due this minute (once). Returns the started run ids."""
        started = []
        for team in self.store.list():
            for i, key in due_slots(team, now):
                if self.fired.get((team["id"], i)) == key:
                    continue
                self.fired[(team["id"], i)] = key
                slot = team["schedule"][i]
                try:
                    res = await self.start(team["id"], slot["task"], {"kind": "schedule", "cron": slot["cron"], "at": key[-5:]})
                    started.append(res["run_id"])
                except TeamError:
                    pass
        return started

    async def loop(self, every: float = 20.0) -> None:
        import asyncio
        while True:
            try:
                await self.tick()
            except Exception:  # a bad team file must never stop the scheduler
                pass
            await asyncio.sleep(every)

    async def on_run_end(self, state) -> None:
        team_id = (state.team or {}).get("id")
        if not team_id:
            return
        try:
            status = {"finished": "done", "gave_up": "gave up"}.get(state.status, state.status)
            self.store.remember_run(team_id, state.title, state.final_result or "", status)
        except TeamError:
            return  # the team was deleted meanwhile
        leftover = state.take_messages()
        if leftover:  # you wrote after it had already finished: start the next run with it
            await self.start(team_id, "\n".join(leftover), {"kind": "message"})
