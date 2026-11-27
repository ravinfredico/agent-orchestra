"""Shared run state: agents, the task board, usage, and the event log.

Every change is logged as one event `{seq, run_id, t, type, ...}` to `runs/<id>/log.jsonl`.
That file is the source of truth: the server, the web app and the replay page all read it.
Listeners (the CLI printer, the server's SSE fan-out) get each event right after it is written.
"""

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Config

TERMINAL_EVENTS = {"finished", "run_failed", "run_stopped", "run_interrupted"}


def make_run_id() -> str:
    """`YYYYmmdd-HHMMSS-xxxxxx`. The random suffix keeps runs started in the same second apart."""
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def auth_mode() -> str:
    """'api_key' when ANTHROPIC_API_KEY is set (billed per use), else 'plan' (Claude plan login)."""
    return "api_key" if os.environ.get("ANTHROPIC_API_KEY") else "plan"


def short_title(task: str, words: int = 6) -> str:
    first_line = task.strip().splitlines()[0] if task.strip() else "Untitled run"
    parts = first_line.split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


@dataclass
class AgentSpec:
    name: str
    role: str
    system_prompt: str
    tools: list[str]               # catalog ids
    color_index: int = 0
    model: str = ""                # tier: haiku | sonnet | opus
    tier_reason: str = ""


@dataclass
class Task:
    task_id: str
    agent: str
    task: str
    done_when: str
    title: str = ""
    status: str = "pending"        # pending | running | checking | retrying | done | failed | replaced
    replaces: str = ""             # id of a failed task this one supersedes
    replaced_by: str = ""
    attempts: int = 0
    output: str = ""
    feedback: str = ""
    short: str = ""                # checker's few-word reason, for the task card
    tier: str = ""                 # model tier of the current attempt
    tier_reason: str = ""
    depends_on: list[str] = field(default_factory=list)  # tasks that must pass first
    owns: list[str] = field(default_factory=list)        # files only this task may write while it runs


@dataclass
class Usage:
    model_calls: int = 0
    turns: int = 0
    cost_usd: float = 0.0
    assignments: int = 0


Listener = Callable[[dict], None]


class RunState:
    def __init__(self, task: str, config: Config, run_dir: Path, workspace: Path | None = None, *,
                 repo: str | None = None, branch: str | None = None, parent_id: str | None = None,
                 listeners: list[Listener] | None = None):
        self.task = task
        self.title = short_title(task)
        self.config = config
        self.run_dir = Path(run_dir)
        self.run_id = self.run_dir.name
        self.run_dir.mkdir(parents=True, exist_ok=True)
        # workspace = your existing repo (--repo), or a fresh folder inside the run
        self.workspace = Path(workspace) if workspace else (self.run_dir / "workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.repo = repo
        self.branch = branch
        self.parent_id = parent_id
        self.auth_mode = auth_mode()
        self.created_at = round(time.time(), 2)
        self.agents: dict[str, AgentSpec] = {}
        self.board: dict[str, Task] = {}
        self.usage = Usage()
        self.final_result: str | None = None
        self.pending_finish: dict | None = None
        self.status = "created"    # created | running | finished | gave_up | failed | stopped | interrupted
        self.error: dict | None = None
        self.approvals = None      # ApprovalBroker, set by the orchestrator
        self.tools = None          # OrchestraTools, set by the orchestrator
        self._seq = 0
        self._log_path = self.run_dir / "log.jsonl"
        self._listeners: list[Listener] = list(listeners or [])
        self.write_meta()

    # ---- listeners -----------------------------------------------------------

    def add_listener(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn: Listener) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    # ---- budget -------------------------------------------------------------

    def budget_problem(self) -> str | None:
        """Return a reason string if the run is out of budget, else None."""
        b = self.config.budget
        if self.usage.cost_usd >= b.max_cost_usd:
            return f"cost limit reached (${self.usage.cost_usd:.2f} of ${b.max_cost_usd:.2f})"
        if self.usage.assignments >= b.max_assignments:
            return f"assignment limit reached ({b.max_assignments})"
        return None

    def record_usage(self, turns: int, cost: float | None, *, agent: str = "", role: str = "",
                     model: str = "", task_id: str = "") -> None:
        """Add one model call. agent/role/model/task_id say who spent it, for the breakdown.

        role is orchestrator, worker or checker; agent is the worker's name, or the role itself."""
        self.usage.model_calls += 1
        self.usage.turns += turns or 0
        delta = cost or 0.0
        self.usage.cost_usd += delta
        self.log("usage", cost_usd=round(self.usage.cost_usd, 4), delta_usd=round(delta, 4),
                 model_calls=self.usage.model_calls, turns=self.usage.turns,
                 assignments=self.usage.assignments, agent=agent or role, role=role, model=model,
                 task_id=task_id)

    # ---- board ---------------------------------------------------------------

    def board_summary(self) -> dict:
        return {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "agent": t.agent,
                    "status": t.status,
                    "attempts": t.attempts,
                    "tier": t.tier,
                    "done_when": t.done_when,
                    "last_feedback": t.feedback[:500],
                }
                for t in self.board.values()
            ],
            "agents": list(self.agents),
            "usage": asdict(self.usage),
            "budget_left": {
                "agents": self.config.budget.max_agents - len(self.agents),
                "assignments": self.config.budget.max_assignments - self.usage.assignments,
                "cost_usd": round(self.config.budget.max_cost_usd - self.usage.cost_usd, 2),
            },
        }

    def unfinished(self) -> list[Task]:
        return [t for t in self.board.values() if t.status not in ("done", "replaced")]

    def save_board(self) -> None:
        data = {
            "task": self.task,
            "status": self.status,
            "agents": {k: asdict(v) for k, v in self.agents.items()},
            "board": {k: asdict(v) for k, v in self.board.items()},
            "usage": asdict(self.usage),
        }
        (self.run_dir / "board.json").write_text(json.dumps(data, indent=2))

    def meta(self) -> dict:
        return {
            "id": self.run_id, "task": self.task, "title": self.title,
            "options": self.config.to_options(), "parent_id": self.parent_id,
            "repo": self.repo, "branch": self.branch, "auth_mode": self.auth_mode,
            "workspace": str(self.workspace), "created_at": self.created_at,
        }

    def write_meta(self) -> None:
        (self.run_dir / "meta.json").write_text(json.dumps(self.meta(), indent=2))

    # ---- events --------------------------------------------------------------

    def log(self, event: str, **data: Any) -> dict:
        self._seq += 1
        entry = {"seq": self._seq, "run_id": self.run_id, "t": round(time.time(), 3), "type": event, **data}
        with self._log_path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        self._track_status(entry)
        for fn in list(self._listeners):
            try:
                fn(entry)
            except Exception:  # a broken listener must never stop the run
                pass
        return entry

    def _track_status(self, e: dict) -> None:
        t = e["type"]
        if t == "run_started":
            self.status = "running"
        elif t == "finished":
            self.status = "gave_up" if e.get("give_up") else "finished"
        elif t == "run_failed":
            self.status = "failed"
        elif t == "run_stopped":
            self.status = "stopped"
        elif t == "run_interrupted":
            self.status = "interrupted"


# ---- CLI output ----------------------------------------------------------------

_COLORS = {
    "agent_created": "\033[95m",
    "task_assigned": "\033[94m",
    "task_passed": "\033[92m",
    "task_failed": "\033[91m",
    "attempt_failed": "\033[93m",
    "orchestrator_said": "\033[96m",
    "approval_requested": "\033[93m",
    "nudge": "\033[93m",
    "finished": "\033[92m",
    "budget_exhausted": "\033[91m",
    "run_failed": "\033[91m",
}
_QUIET = {"usage"}


def cli_printer(entry: dict) -> None:
    """Pretty, colored one-line output for the terminal. Registered by main.py only."""
    event = entry["type"]
    if event in _QUIET:
        return
    data = {k: v for k, v in entry.items() if k not in ("seq", "run_id", "t", "type")}
    color = _COLORS.get(event, "\033[90m")
    short = {k: (str(v)[:160] + "…" if len(str(v)) > 160 else v) for k, v in data.items()}
    body = "  ".join(f"{k}={v}" for k, v in short.items())
    print(f"{color}[{event}]\033[0m {body}", flush=True)


def read_events(run_dir: Path, after: int = 0) -> list[dict]:
    """All events in a run's log with seq > after."""
    path = Path(run_dir) / "log.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("seq", 0) > after:
            out.append(e)
    return out
