"""SQLite index of runs, for fast history, search and filters. Rebuildable from runs/*/log.jsonl.

    python -m server.index --rebuild
"""

import json
import sqlite3
import sys
import threading
from pathlib import Path

from .summary import fold, summary

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, title TEXT, task TEXT, status TEXT, needs_approval INTEGER,
  created_at REAL, ended_at REAL, duration_s INTEGER, cost_usd REAL, agents TEXT,
  tasks_total INTEGER, tasks_passed INTEGER, repo TEXT, branch TEXT, parent_id TEXT
);
CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at DESC);
CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(id UNINDEXED, title, task);
"""
COLS = ["id", "title", "task", "status", "needs_approval", "created_at", "ended_at", "duration_s", "cost_usd",
        "agents", "tasks_total", "tasks_passed", "repo", "branch", "parent_id"]


class RunIndex:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def upsert(self, s: dict) -> None:
        row = {**s, "agents": json.dumps(s.get("agents", [])), "needs_approval": int(bool(s.get("needs_approval")))}
        with self._lock, self._db:
            self._db.execute(f"INSERT OR REPLACE INTO runs ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                             [row.get(c) for c in COLS])
            self._db.execute("DELETE FROM runs_fts WHERE id = ?", (s["id"],))
            self._db.execute("INSERT INTO runs_fts (id, title, task) VALUES (?, ?, ?)", (s["id"], s.get("title", ""), s.get("task", "")))

    def delete(self, run_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            self._db.execute("DELETE FROM runs_fts WHERE id = ?", (run_id,))

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._row(r) if r else None

    def search(self, q: str = "", status: str = "", repo: bool | None = None, limit: int = 50,
               before: float | None = None) -> list[dict]:
        sql, args = "SELECT runs.* FROM runs", []
        where = []
        if q.strip():
            terms = " ".join('"' + w.replace('"', "") + '"*' for w in q.split())
            sql += " JOIN runs_fts ON runs_fts.id = runs.id"
            where.append("runs_fts MATCH ?")
            args.append(terms)
        if status:
            statuses = status.split(",")
            where.append(f"runs.status IN ({','.join('?' * len(statuses))})")
            args += statuses
        if repo is True:
            where.append("runs.repo IS NOT NULL AND runs.repo != ''")
        if before is not None:
            where.append("runs.created_at < ?")
            args.append(before)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY runs.created_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["agents"] = json.loads(d["agents"] or "[]")
        d["needs_approval"] = bool(d["needs_approval"])
        return d

    def rebuild(self, runs_dir: Path) -> int:
        with self._lock, self._db:
            self._db.execute("DELETE FROM runs")
            self._db.execute("DELETE FROM runs_fts")
        n = 0
        for d in sorted(Path(runs_dir).iterdir()) if Path(runs_dir).exists() else []:
            if d.is_dir() and (d / "log.jsonl").exists():
                self.upsert(summary(fold(d)))
                n += 1
        return n


if __name__ == "__main__":
    runs = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("runs")
    if "--rebuild" in sys.argv:
        print(f"Indexed {RunIndex(runs / 'index.db').rebuild(runs)} runs.")
