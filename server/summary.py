"""Fold a run's event log into the shapes the API returns (RunSummary, RunDetail).

The log is the source of truth, so this works the same for live, finished and old runs.
"""

import json
from pathlib import Path

from orchestra.state import TERMINAL_EVENTS, read_events

STATUS_FOR = {"finished": None, "run_failed": "failed", "run_stopped": "stopped", "run_interrupted": "interrupted"}


def fold(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}
    events = read_events(run_dir)
    d = {
        "id": run_dir.name, "title": meta.get("title") or run_dir.name, "task": meta.get("task", ""),
        "status": "running" if events else "created", "needs_approval": False,
        "created_at": meta.get("created_at") or (events[0]["t"] if events else None), "ended_at": None,
        "duration_s": 0, "cost_usd": 0.0, "agents": [], "tasks_total": 0, "tasks_passed": 0,
        "repo": meta.get("repo"), "branch": meta.get("branch"), "parent_id": meta.get("parent_id"),
        "auth_mode": meta.get("auth_mode"), "options": meta.get("options", {}),
        "board": [], "files": [], "final": "", "error": None, "pending_approvals": [], "last_seq": 0,
        "model_calls": 0,
    }
    agents: dict[str, dict] = {}
    board: dict[str, dict] = {}
    files: dict[str, dict] = {}
    pending: dict[str, dict] = {}
    for e in events:
        t = e["type"]
        d["last_seq"] = e["seq"]
        if t == "agent_created":
            agents[e["name"]] = {"name": e["name"], "role": e.get("role", ""), "tools": e.get("tools", []),
                                 "model": e.get("model", ""), "color_index": e.get("color_index", len(agents)),
                                 "status": "idle"}
        elif t == "task_assigned":
            board[e["task_id"]] = {"task_id": e["task_id"], "title": e.get("title", ""), "agent": e["agent"],
                                   "task": e.get("task", ""), "done_when": e.get("done_when", ""),
                                   "replaces": e.get("replaces", ""), "replaced_by": "", "status": "pending",
                                   "attempts": 0, "feedback": "", "short": "", "history": []}
        elif t == "attempt_started" and e["task_id"] in board:
            b = board[e["task_id"]]
            b["attempts"] = e["attempt"]
            b["status"] = "running" if e["attempt"] == 1 else "retrying"
            if b["agent"] in agents:
                agents[b["agent"]]["status"] = "working"
        elif t == "checker_started" and e["task_id"] in board:
            board[e["task_id"]]["status"] = "checking"
            a = agents.get(board[e["task_id"]]["agent"])
            if a:
                a["status"] = "waiting"
        elif t == "attempt_failed" and e["task_id"] in board:
            b = board[e["task_id"]]
            b.update(status="retrying", feedback=e.get("reason", ""), short=e.get("short", ""))
            b["history"].append({"attempt": e["attempt"], "passed": False, "reason": e.get("reason", ""), "short": e.get("short", "")})
        elif t == "task_passed" and e["task_id"] in board:
            b = board[e["task_id"]]
            b.update(status="done", feedback=e.get("reason", ""), short=e.get("short", ""))
            b["history"].append({"attempt": e["attempt"], "passed": True, "reason": e.get("reason", ""), "short": e.get("short", "")})
            if b["agent"] in agents:
                agents[b["agent"]]["status"] = "idle"
        elif t == "task_failed" and e["task_id"] in board:
            board[e["task_id"]]["status"] = "failed"
            a = agents.get(board[e["task_id"]]["agent"])
            if a:
                a["status"] = "idle"
        elif t == "task_replaced" and e["task_id"] in board:
            board[e["task_id"]].update(status="replaced", replaced_by=e.get("by", ""))
        elif t == "file_written":
            f = files.get(e["path"])
            files[e["path"]] = {"path": e["path"], "agent": e.get("agent", ""),
                                "versions": (f["versions"] + 1) if f else 1, "t": e["t"]}
        elif t == "usage":
            d["cost_usd"] = e.get("cost_usd", d["cost_usd"])
            d["model_calls"] = e.get("model_calls", d["model_calls"])
        elif t == "approval_requested":
            pending[e["approval_id"]] = {k: e.get(k) for k in ("approval_id", "task_id", "agent", "tool", "catalog_id", "preview")}
        elif t == "approval_resolved":
            pending.pop(e["approval_id"], None)
        elif t == "finished":
            d["status"] = "gave_up" if e.get("give_up") else "finished"
            d["final"] = e.get("result", "")
        elif t in STATUS_FOR and STATUS_FOR[t]:
            d["status"] = STATUS_FOR[t]
            if t == "run_failed":
                d["error"] = {"error": e.get("error"), "kind": e.get("kind"), "hint": e.get("hint")}
        if t in TERMINAL_EVENTS:
            d["ended_at"] = e["t"]
            pending.clear()
    if d["created_at"]:
        end = d["ended_at"] or (events[-1]["t"] if events else d["created_at"])
        d["duration_s"] = round(end - d["created_at"])
    if not d["final"] and (run_dir / "final.md").exists():
        d["final"] = (run_dir / "final.md").read_text()
    d["agents"] = list(agents.values())
    d["board"] = list(board.values())
    d["files"] = sorted(files.values(), key=lambda f: f["path"])
    d["tasks_total"] = len(board)
    d["tasks_passed"] = sum(1 for b in board.values() if b["status"] == "done")
    d["pending_approvals"] = list(pending.values())
    d["needs_approval"] = bool(pending)
    return d


SUMMARY_KEYS = ("id", "title", "task", "status", "needs_approval", "created_at", "ended_at", "duration_s",
                "cost_usd", "agents", "tasks_total", "tasks_passed", "repo", "branch", "parent_id")


def summary(detail: dict) -> dict:
    s = {k: detail[k] for k in SUMMARY_KEYS}
    s["agents"] = [{"name": a["name"], "color_index": a["color_index"]} for a in detail["agents"]]
    return s
