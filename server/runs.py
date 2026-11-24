"""RunManager: starts runs as background asyncio tasks, fans their events out to SSE subscribers,
keeps the SQLite index current, and recovers after a restart."""

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from orchestra import fake
from orchestra.catalog import Catalog, load_catalog
from orchestra.config import Config
from orchestra.gitsafe import RepoError, check_allowed, prepare_repo
from orchestra.orchestrator import continue_task, create_run, execute_run, follow_up_task
from orchestra.runner import run_agent
from orchestra.state import TERMINAL_EVENTS, RunState, read_events

from .index import RunIndex
from .summary import fold, summary


class RunError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class RunHandle:
    state: RunState
    task: asyncio.Task | None = None
    queues: set = field(default_factory=set)


class RunManager:
    def __init__(self, runs_dir: Path = Path("runs"), *, runner=None, client_factory=None,
                 catalog: Catalog | None = None, notify=None, fake_mode: bool | None = None,
                 fake_delay: float = 0.7, repos_root: str | None = None):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.index = RunIndex(self.runs_dir / "index.db")
        self.fake_mode = (os.environ.get("ORCHESTRA_FAKE_RUNNER") == "1") if fake_mode is None else fake_mode
        self.fake_delay = fake_delay
        self.runner = runner
        self.client_factory = client_factory
        self.catalog = catalog or (fake.demo_catalog() if self.fake_mode else load_catalog())
        self.notify = notify
        self.repos_root = repos_root if repos_root is not None else os.environ.get("REPOS_ROOT")
        self.active: dict[str, RunHandle] = {}

    # ---- lifecycle ------------------------------------------------------------

    def recover(self) -> int:
        """Mark runs that never ended (server stopped mid-run) as interrupted, and rebuild the index."""
        n = 0
        for d in sorted(self.runs_dir.iterdir()):
            if not (d.is_dir() and (d / "log.jsonl").exists()) or d.name in self.active:
                continue
            events = read_events(d)
            if events and events[-1]["type"] not in TERMINAL_EVENTS:
                last = events[-1]
                with (d / "log.jsonl").open("a") as f:
                    f.write(json.dumps({"seq": last["seq"] + 1, "run_id": d.name, "t": round(time.time(), 3),
                                        "type": "run_interrupted"}) + "\n")
                n += 1
        self.index.rebuild(self.runs_dir)
        return n

    async def start(self, task: str, options: dict | None = None, parent: dict | None = None) -> str:
        task = (task or "").strip()
        options = dict(options or {})
        parent_id, seed, mode = None, None, None
        if parent:
            parent_id, mode = parent.get("run_id"), parent.get("mode")
            pdir = self.runs_dir / str(parent_id)
            if not (pdir / "meta.json").exists():
                raise RunError(404, "Parent run not found")
            pmeta = fold(pdir)
            if pmeta.get("repo"):
                raise RunError(400, "Continue and follow-up are not supported for repo runs yet. Start a new run in the repo.")
            if mode == "continue":
                task = continue_task(pdir)
                base = pmeta.get("options") or {}
                options = {**base, **options}
            elif mode == "follow_up":
                if not task:
                    raise RunError(400, "A follow-up needs a task")
                task = follow_up_task(pdir, task)
            else:
                raise RunError(400, "parent.mode must be continue or follow_up")
            seed = pdir / "workspace"
        if not task:
            raise RunError(400, "Task is empty")

        config = Config.from_options(options)
        workspace, repo, branch = None, None, None
        if options.get("repo"):
            repo_path = Path(os.path.expanduser(options["repo"])).resolve()
            try:
                check_allowed(repo_path, Path(self.repos_root) if self.repos_root else None)
            except RepoError as e:
                raise RunError(400, str(e))
            if any(h.state.repo == str(repo_path) for h in self.active.values()):
                raise RunError(409, "Another run is already working in that repository.")
            try:
                branch = prepare_repo(repo_path, bool(options.get("allow_dirty")), verbose=False)
            except RepoError as e:
                raise RunError(400, str(e))
            workspace, repo = repo_path, str(repo_path)
            seed = None

        state = create_run(task, config, self.runs_dir, workspace, repo=repo, branch=branch,
                           parent_id=parent_id, seed_from=seed, listeners=[])
        handle = RunHandle(state=state)
        self.active[state.run_id] = handle
        state.add_listener(lambda e, h=handle: self._on_event(h, e))
        self.index.upsert(summary(fold(state.run_dir)))
        handle.task = asyncio.create_task(self._execute(handle), name=f"run-{state.run_id}")
        return state.run_id

    async def _execute(self, handle: RunHandle) -> None:
        state = handle.state
        if self.fake_mode:
            make_runner, script = fake.pick_demo(state.task)
            runner = self.runner or make_runner(self.fake_delay)
            factory = self.client_factory or fake.fake_client_factory(script, {"state": state})
        else:
            runner = self.runner or run_agent
            factory = self.client_factory
        kwargs = {"runner": runner, "catalog": self.catalog, "interactive": True, "notify": self.notify}
        if factory:
            kwargs["client_factory"] = factory
        try:
            await execute_run(state, **kwargs)
        except asyncio.CancelledError:
            pass
        finally:
            self.index.upsert(summary(fold(state.run_dir)))
            self.active.pop(state.run_id, None)
            for q in list(handle.queues):
                q.put_nowait(None)

    def _on_event(self, handle: RunHandle, e: dict) -> None:
        for q in list(handle.queues):
            q.put_nowait(e)
        t = e["type"]
        if t in ("run_started", "agent_created", "task_passed", "approval_requested", "approval_resolved") \
                or t in TERMINAL_EVENTS:
            self.index.upsert(summary(fold(handle.state.run_dir)))
        if self.notify and t in ("finished", "run_failed"):
            try:
                self.notify(e)
            except Exception:
                pass

    async def stop(self, run_id: str) -> None:
        h = self.active.get(run_id)
        if not h or not h.task:
            raise RunError(409, "Run is not running")
        h.task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(h.task), timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    def resolve_approval(self, run_id: str, approval_id: str, approve: bool) -> None:
        h = self.active.get(run_id)
        if not h or not h.state.approvals or not h.state.approvals.resolve(approval_id, approve):
            raise RunError(404, "No pending approval with that id")

    def delete(self, run_id: str) -> None:
        if run_id in self.active:
            raise RunError(409, "Stop the run before deleting it")
        d = self.run_dir(run_id)
        shutil.rmtree(d)
        self.index.delete(run_id)

    # ---- reading ------------------------------------------------------------------

    def run_dir(self, run_id: str) -> Path:
        d = (self.runs_dir / run_id).resolve()
        if d.parent != self.runs_dir.resolve() or not (d / "meta.json").exists():
            raise RunError(404, "Run not found")
        return d

    def detail(self, run_id: str) -> dict:
        return fold(self.run_dir(run_id))

    def workspace(self, run_id: str) -> Path:
        d = self.run_dir(run_id)
        detail = fold(d)
        return Path(detail["repo"]) if detail.get("repo") else d / "workspace"

    def subscribe(self, run_id: str) -> asyncio.Queue | None:
        h = self.active.get(run_id)
        if not h:
            return None
        q: asyncio.Queue = asyncio.Queue()
        h.queues.add(q)
        return q

    def unsubscribe(self, run_id: str, q) -> None:
        h = self.active.get(run_id)
        if h:
            h.queues.discard(q)

    def status(self) -> dict:
        running = []
        for rid in list(self.active):
            d = fold(self.runs_dir / rid)
            running.append({"id": rid, "title": d["title"], "status": d["status"], "elapsed_s": d["duration_s"],
                            "cost_usd": d["cost_usd"], "agents": len(d["agents"]), "needs_approval": d["needs_approval"]})
        ended = [r for r in self.index.search(limit=20) if r["id"] not in self.active and r["ended_at"]]
        last = ended[0] if ended else None
        return {"running": running,
                "last": {k: last[k] for k in ("id", "title", "status", "ended_at")} if last else None}
