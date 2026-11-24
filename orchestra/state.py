"""Shared run state: created agents, the task board, usage counters, and logging."""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

from .config import Config


@dataclass
class AgentSpec:
    name: str
    role: str
    system_prompt: str
    tools: list[str]


@dataclass
class Task:
    task_id: str
    agent: str
    task: str
    done_when: str
    status: str = "pending"          # pending | running | done | failed | replaced
    replaces: str = ""               # id of a failed task this one supersedes
    attempts: int = 0
    output: str = ""
    feedback: str = ""


@dataclass
class Usage:
    model_calls: int = 0
    turns: int = 0
    cost_usd: float = 0.0
    assignments: int = 0


class RunState:
    def __init__(self, task: str, config: Config, run_dir: Path, workspace: Path | None = None):
        self.task = task
        self.config = config
        self.run_dir = run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        # workspace = your existing repo (--repo), or a fresh folder inside the run
        self.workspace = workspace or (run_dir / "workspace")
        self.repo_mode = workspace is not None
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.agents: dict[str, AgentSpec] = {}
        self.board: dict[str, Task] = {}
        self.usage = Usage()
        self.final_result: str | None = None
        self.status = "running"          # running | finished | gave_up | incomplete | error | stopped
        self.listeners: list[Callable[[dict], None]] = []   # e.g. the web UI's live event stream
        self.quiet = False               # True: don't print events to the console
        self._log_path = run_dir / "log.jsonl"
        self._seq = 0

    # ---- budget -------------------------------------------------------------

    def budget_problem(self) -> str | None:
        """Return a reason string if the run is out of budget, else None."""
        b = self.config.budget
        if self.usage.cost_usd >= b.max_cost_usd:
            return f"cost limit reached (${self.usage.cost_usd:.2f} of ${b.max_cost_usd:.2f})"
        if self.usage.assignments >= b.max_assignments:
            return f"assignment limit reached ({b.max_assignments})"
        return None

    def record_usage(self, turns: int, cost: float | None) -> None:
        self.usage.model_calls += 1
        self.usage.turns += turns or 0
        self.usage.cost_usd += cost or 0.0
        self.log("usage", **asdict(self.usage))

    # ---- board ---------------------------------------------------------------

    def board_summary(self) -> dict:
        return {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "agent": t.agent,
                    "status": t.status,
                    "attempts": t.attempts,
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

    def snapshot(self) -> dict:
        """Everything about the run right now. Written to board.json and served to the web UI."""
        return {
            "task": self.task,
            "status": self.status,
            "workspace": str(self.workspace),
            "agents": {k: asdict(v) for k, v in self.agents.items()},
            "board": {k: asdict(v) for k, v in self.board.items()},
            "usage": asdict(self.usage),
            "budget": asdict(self.config.budget),
            "final_result": self.final_result,
        }

    def save_board(self) -> None:
        (self.run_dir / "board.json").write_text(json.dumps(self.snapshot(), indent=2))

    # ---- logging -------------------------------------------------------------

    def log(self, event: str, **data) -> None:
        self._seq += 1
        entry = json.loads(json.dumps(
            {"seq": self._seq, "t": round(time.time(), 2), "event": event, **data}, default=str))
        with self._log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        for listener in list(self.listeners):
            try:
                listener(entry)
            except Exception:  # a broken listener must never break the run
                pass
        if not self.quiet and event != "usage":
            print(_pretty(event, data), flush=True)


_COLORS = {
    "agent_created": "\033[95m",
    "task_assigned": "\033[94m",
    "task_passed": "\033[92m",
    "task_failed": "\033[91m",
    "attempt_failed": "\033[93m",
    "orchestrator": "\033[96m",
    "nudge": "\033[93m",
    "finished": "\033[92m",
    "budget": "\033[91m",
    "error": "\033[91m",
}


def _pretty(event: str, data: dict) -> str:
    color = _COLORS.get(event, "\033[90m")
    short = {k: (str(v)[:160] + "…" if len(str(v)) > 160 else v) for k, v in data.items()}
    body = "  ".join(f"{k}={v}" for k, v in short.items())
    return f"{color}[{event}]\033[0m {body}"
