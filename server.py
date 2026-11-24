"""Local web UI: type a task in the browser, press start, watch the run live.

    python server.py            # then open http://127.0.0.1:8000

Binds to 127.0.0.1 only. Bash-enabled runs execute real commands on this machine.
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from orchestra import orchestrator
from orchestra.config import Budget, Config
from orchestra.gitsafe import RepoError, prepare_repo
from orchestra.state import RunState

INDEX = Path(__file__).parent / "web" / "index.html"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "testserver"}  # testserver: FastAPI's TestClient
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
MAX_FILES = 2000
MAX_FILE_BYTES = 512 * 1024


class RunRequest(BaseModel):
    task: str = Field(min_length=1)
    allow_bash: bool = False
    repo: str = ""
    allow_dirty: bool = False
    orchestrator_model: str = "sonnet"
    worker_model: str = "sonnet"
    checker_model: str = "haiku"
    max_cost: float = Field(5.0, gt=0)
    max_agents: int = Field(6, ge=1, le=50)
    max_assignments: int = Field(15, ge=1, le=200)
    max_attempts: int = Field(3, ge=1, le=10)


@dataclass
class ActiveRun:
    state: RunState
    task: asyncio.Task


def create_app(runs_dir: Path = Path("runs"), execute=orchestrator.execute) -> FastAPI:
    """execute is injectable so tests can run without model calls."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Agent Orchestra")
    active: dict[str, ActiveRun] = {}

    # ---- safety: only this machine's browser may talk to us ---------------------
    # Blocks DNS rebinding (Host check) and other websites POSTing to localhost (Origin check),
    # since a started run can execute shell commands.
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
            return JSONResponse({"detail": "forbidden origin"}, status_code=403)
        if request.method == "POST" and request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"detail": "expected application/json"}, status_code=415)
        return await call_next(request)

    # ---- helpers -----------------------------------------------------------------
    def run_dir(run_id: str) -> Path:
        if not run_id.replace("-", "").isalnum() or not (runs_dir / run_id).is_dir():
            raise HTTPException(404, "no such run")
        return runs_dir / run_id

    def snapshot(run_id: str) -> dict:
        if run_id in active:
            data = active[run_id].state.snapshot()
        else:
            d = run_dir(run_id)
            try:
                data = json.loads((d / "board.json").read_text())
            except (OSError, json.JSONDecodeError):
                data = {}
            if data.get("status", "running") == "running":
                data["status"] = "interrupted"   # server stopped while it was running
            if data.get("final_result") is None and (d / "final.md").exists():
                data["final_result"] = (d / "final.md").read_text()
        data["id"] = run_id
        data["active"] = run_id in active
        return data

    def workspace(run_id: str) -> Path:
        ws = snapshot(run_id).get("workspace")
        return Path(ws) if ws else run_dir(run_id) / "workspace"

    # ---- endpoints ---------------------------------------------------------------
    @app.get("/")
    async def index():
        return FileResponse(INDEX)

    @app.post("/api/runs")
    async def start_run(req: RunRequest):
        config = Config(
            orchestrator_model=req.orchestrator_model,
            worker_model=req.worker_model,
            checker_model=req.checker_model,
            allow_bash=req.allow_bash,
            budget=Budget(max_agents=req.max_agents, max_assignments=req.max_assignments,
                          max_attempts_per_task=req.max_attempts, max_cost_usd=req.max_cost),
        )
        ws, branch = None, None
        if req.repo.strip():
            ws = Path(req.repo.strip()).expanduser().resolve()
            try:
                branch = prepare_repo(ws, req.allow_dirty)
            except RepoError as e:
                raise HTTPException(400, str(e))
        state = orchestrator.create_state(req.task, config, runs_dir, ws)
        state.quiet = True
        run_id = state.run_dir.name
        state.log("config", options=req.model_dump(), branch=branch)
        task = asyncio.create_task(execute(state))
        active[run_id] = ActiveRun(state, task)
        task.add_done_callback(lambda _: active.pop(run_id, None))
        return {"id": run_id}

    @app.get("/api/runs")
    async def list_runs():
        out = []
        for d in sorted((p for p in runs_dir.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
            s = snapshot(d.name)
            out.append({
                "id": d.name,
                "task": (s.get("task") or "")[:300],
                "status": s.get("status"),
                "active": s["active"],
                "cost_usd": (s.get("usage") or {}).get("cost_usd", 0.0),
                "tasks": len(s.get("board") or {}),
            })
        return out

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        return snapshot(run_id)

    @app.post("/api/runs/{run_id}/stop")
    async def stop_run(run_id: str):
        run = active.get(run_id)
        if not run:
            raise HTTPException(409, "run is not active")
        run.task.cancel()
        return {"stopping": True}

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request):
        log_path = run_dir(run_id) / "log.jsonl"
        try:
            after = int(request.headers.get("last-event-id") or 0)   # EventSource reconnects
        except ValueError:
            after = 0

        async def stream():
            queue: asyncio.Queue = asyncio.Queue()
            run = active.get(run_id)
            if run:  # subscribe before replaying, so nothing falls in the gap
                run.state.listeners.append(queue.put_nowait)
            try:
                last, ended = after, False
                if log_path.exists():
                    for n, line in enumerate(log_path.read_text().splitlines(), 1):
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        seq = entry.setdefault("seq", n)
                        ended = ended or entry.get("event") == "run_end"
                        if seq > last:
                            last = seq
                            yield f"id: {seq}\ndata: {json.dumps(entry)}\n\n"
                while run and not ended:
                    try:
                        entry = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    if entry["seq"] > last:
                        last = entry["seq"]
                        yield f"id: {last}\ndata: {json.dumps(entry)}\n\n"
                    ended = entry.get("event") == "run_end"
                yield "event: end\ndata: {}\n\n"
            finally:
                if run and queue.put_nowait in run.state.listeners:
                    run.state.listeners.remove(queue.put_nowait)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/runs/{run_id}/files")
    async def list_files(run_id: str):
        root = workspace(run_id)
        files = []
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                rel = p.relative_to(root)
                if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
                    continue
                files.append({"path": rel.as_posix(), "size": p.stat().st_size})
                if len(files) >= MAX_FILES:
                    break
        return {"root": str(root), "files": files, "truncated": len(files) >= MAX_FILES}

    @app.get("/api/runs/{run_id}/file")
    async def file_content(run_id: str, path: str):
        root = workspace(run_id).resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "no such file")
        raw = target.read_bytes()[:MAX_FILE_BYTES]
        if b"\0" in raw[:8192]:
            return {"path": path, "binary": True, "content": "", "truncated": False}
        return {"path": path, "binary": False, "content": raw.decode("utf-8", errors="replace"),
                "truncated": target.stat().st_size > MAX_FILE_BYTES}

    return app


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="Agent Orchestra local web UI")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    a = p.parse_args()
    print(f"Agent Orchestra UI on http://127.0.0.1:{a.port}  (local only)")
    uvicorn.run(create_app(a.runs_dir), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
