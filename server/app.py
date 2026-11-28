"""FastAPI app: REST + SSE for ChaCha PA, and the built web app (web/dist)."""

import asyncio
import io
import json
import mimetypes
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from orchestra import builder, fake
from orchestra.playbooks import load_playbooks
from orchestra.state import TERMINAL_EVENTS, auth_mode, read_events

from . import auth, studio
from .runs import RunError, RunManager
from .teams import TeamError, TeamRunner, TeamStore, room_items

VERSION = "0.1.0"
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
MAX_FILE = 2 * 1024 * 1024
ZIP_SKIP = {".agents", ".git", "node_modules", "__pycache__", ".venv"}
TEXT_TYPES = {".md": "text/markdown", ".py": "text/x-python", ".ts": "text/plain", ".tsx": "text/plain",
              ".json": "application/json", ".log": "text/plain", ".txt": "text/plain", ".csv": "text/csv",
              ".yaml": "text/plain", ".yml": "text/plain", ".toml": "text/plain", ".js": "text/plain",
              ".html": "text/plain", ".css": "text/plain", ".sh": "text/plain"}


def create_app(manager: RunManager | None = None, runs_dir: Path = Path("runs"), web_dist: Path = WEB_DIST,
               teams_dir: Path | None = None, schedule: bool = True) -> FastAPI:
    mgr = manager or RunManager(runs_dir)

    store = TeamStore(teams_dir or mgr.runs_dir.parent / "teams")  # teams/ next to runs/
    teams = TeamRunner(store, mgr, lambda: [e.id for e in mgr.catalog.entries if e.enabled])

    @asynccontextmanager
    async def lifespan(app):
        mgr.recover()
        scheduler = asyncio.create_task(teams.loop()) if schedule else None
        yield
        if scheduler:
            scheduler.cancel()
        for h in list(mgr.active.values()):
            if h.task:
                h.task.cancel()

    app = FastAPI(title="ChaCha PA", version=VERSION, lifespan=lifespan)
    app.state.manager = mgr
    app.state.teams = teams
    guard = [Depends(auth.require_auth)]

    @app.exception_handler(RunError)
    async def run_error(_, exc: RunError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(TeamError)
    async def team_error(_, exc: TeamError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    # ---- auth & health ---------------------------------------------------------

    @app.post("/api/login")
    async def login(body: dict = Body(...)):
        if not auth.app_token():
            return {"ok": True}
        if not auth.token_ok(str(body.get("token", ""))):
            raise HTTPException(401, "Wrong token")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(auth.COOKIE, auth.app_token(), httponly=True, samesite="strict", secure=False,
                        max_age=60 * 60 * 24 * 30)
        return resp

    @app.get("/api/health")
    async def health():
        return {"ok": True, "auth_mode": auth_mode(), "version": VERSION, "fake_mode": mgr.fake_mode,
                "auth_required": bool(auth.app_token())}

    @app.get("/api/catalog", dependencies=guard)
    async def catalog():
        return [e.public() for e in mgr.catalog.entries]

    @app.get("/api/playbooks", dependencies=guard)
    async def playbooks():
        return [{"id": b.id, "title": b.title, "when": b.when} for b in load_playbooks().values()]

    # ---- runs ---------------------------------------------------------------------

    @app.post("/api/runs", dependencies=guard, status_code=201)
    async def start_run(body: dict = Body(...)):
        run_id = await mgr.start(body.get("task", ""), body.get("options") or {}, body.get("parent"))
        d = mgr.detail(run_id)
        return {"id": run_id, "status": d["status"], "created_at": d["created_at"]}

    @app.get("/api/runs", dependencies=guard)
    async def list_runs(q: str = "", status: str = "", repo: bool | None = None, limit: int = Query(50, le=200),
                        before: float | None = None):
        runs = mgr.index.search(q=q, status=status, repo=repo, limit=limit + 1, before=before)
        nxt = runs[limit - 1]["created_at"] if len(runs) > limit else None
        return {"runs": runs[:limit], "next": nxt}

    @app.get("/api/runs/{run_id}", dependencies=guard)
    async def get_run(run_id: str):
        d = mgr.detail(run_id)
        d["active"] = run_id in mgr.active
        return d

    @app.get("/api/runs/{run_id}/events", dependencies=guard)
    async def events(run_id: str, request: Request, after: int = 0,
                     last_event_id: str | None = Header(None, alias="Last-Event-ID")):
        run_dir = mgr.run_dir(run_id)
        start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

        async def gen():
            q = mgr.subscribe(run_id)        # subscribe first so nothing falls in the gap
            last = start
            try:
                for e in read_events(run_dir, after=start):
                    last = e["seq"]
                    yield {"id": str(e["seq"]), "event": e["type"], "data": json.dumps(e)}
                    if e["type"] in TERMINAL_EVENTS:
                        yield {"event": "end", "data": "{}"}
                        return
                if q is None:                 # not running and no terminal event (shouldn't happen)
                    yield {"event": "end", "data": "{}"}
                    return
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        e = await asyncio.wait_for(q.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    if e is None:
                        yield {"event": "end", "data": "{}"}
                        return
                    if e["seq"] <= last:
                        continue
                    last = e["seq"]
                    yield {"id": str(e["seq"]), "event": e["type"], "data": json.dumps(e)}
                    if e["type"] in TERMINAL_EVENTS:
                        yield {"event": "end", "data": "{}"}
                        return
            finally:
                if q is not None:
                    mgr.unsubscribe(run_id, q)

        return EventSourceResponse(gen(), ping=15)

    @app.post("/api/runs/{run_id}/stop", dependencies=guard, status_code=202)
    async def stop(run_id: str):
        await mgr.stop(run_id)
        return {"status": "stopping"}

    @app.post("/api/runs/{run_id}/approvals/{approval_id}", dependencies=guard)
    async def approval(run_id: str, approval_id: str, body: dict = Body(...)):
        decision = body.get("decision")
        if decision not in ("approve", "deny"):
            raise HTTPException(400, "decision must be approve or deny")
        mgr.resolve_approval(run_id, approval_id, decision == "approve")
        return {"ok": True}

    @app.post("/api/runs/{run_id}/continue", dependencies=guard, status_code=201)
    async def cont(run_id: str, body: dict = Body(default={})):
        extra = float(body.get("extra_budget_usd") or 2.0)
        new_id = await mgr.start("", {"max_cost": extra}, {"run_id": run_id, "mode": "continue"})
        return {"id": new_id}

    @app.delete("/api/runs/{run_id}", dependencies=guard, status_code=204)
    async def delete(run_id: str):
        mgr.delete(run_id)
        return Response(status_code=204)

    # ---- files ----------------------------------------------------------------------

    def safe_path(run_id: str, rel: str) -> Path:
        root = mgr.workspace(run_id).resolve()
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise HTTPException(400, "Path is outside the workspace")
        return p

    @app.get("/api/runs/{run_id}/files", dependencies=guard)
    async def files(run_id: str):
        root = mgr.workspace(run_id)
        authors = {f["path"]: f for f in mgr.detail(run_id)["files"]}
        out = []
        if root.exists():
            for p in sorted(root.rglob("*")):
                rel = p.relative_to(root)
                if any(part in ZIP_SKIP for part in rel.parts) or not p.is_file():
                    continue
                st = p.stat()
                a = authors.get(str(rel), {})
                out.append({"path": str(rel), "size": st.st_size, "mtime": st.st_mtime,
                            "agent": a.get("agent", ""), "versions": a.get("versions", 1)})
        return out

    @app.get("/api/runs/{run_id}/files/{path:path}", dependencies=guard)
    async def file(run_id: str, path: str):
        p = safe_path(run_id, path)
        if not p.is_file():
            raise HTTPException(404, "File not found")
        if p.stat().st_size > MAX_FILE:
            raise HTTPException(413, "File is larger than 2 MB")
        ctype = TEXT_TYPES.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "text/plain"
        try:
            return PlainTextResponse(p.read_text(), media_type=ctype)
        except UnicodeDecodeError:
            return FileResponse(p, media_type=ctype)

    @app.get("/api/runs/{run_id}/zip", dependencies=guard)
    async def zip_run(run_id: str):
        root = mgr.workspace(run_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob("*")) if root.exists() else []:
                rel = p.relative_to(root)
                if p.is_file() and not any(part in ZIP_SKIP for part in rel.parts):
                    z.write(p, str(rel))
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'})

    # ---- widget ---------------------------------------------------------------------

    @app.post("/api/runs/{run_id}/messages", dependencies=guard, status_code=202)
    async def steer_run(run_id: str, body: dict = Body(...)):
        mgr.steer(run_id, str(body.get("text", "")))
        return {"ok": True}

    # ---- teams (M8) ---------------------------------------------------------------

    def catalog_ids() -> list[str]:
        return teams.catalog_ids()

    def team_out(t: dict) -> dict:
        return {**t, "active_run": teams.active_run(t["id"]), **builder.review(t, mgr.catalog)}

    # ---- video studio (M10): videos a team made, posted by you by hand --------------------

    def studio_items(team_id: str) -> list[dict]:
        store.get(team_id)
        return studio.items(teams.run_dirs(team_id, limit=200), mgr.workspace, studio.load_posted(store.root / team_id))

    @app.get("/api/teams/{team_id}/studio", dependencies=guard)
    async def team_studio(team_id: str):
        return {"items": studio_items(team_id)}

    @app.post("/api/teams/{team_id}/studio/{run_id}/{name}/posted", dependencies=guard)
    async def studio_posted(team_id: str, run_id: str, name: str, body: dict = Body(...)):
        item_id = f"{run_id}/{name}"
        if not any(i["id"] == item_id for i in studio_items(team_id)):
            raise HTTPException(404, "Video not found")
        studio.set_posted(store.root / team_id, item_id, time.time() if body.get("posted", True) else None)
        return next(i for i in studio_items(team_id) if i["id"] == item_id)

    @app.get("/api/teams/{team_id}/studio/{run_id}/{name}.mp4", dependencies=guard)
    async def studio_video(team_id: str, run_id: str, name: str):
        item = next((i for i in studio_items(team_id) if i["id"] == f"{run_id}/{name}" and i["video"]), None)
        if not item:
            raise HTTPException(404, "Video not found")
        return FileResponse(safe_path(run_id, item["video"]), media_type="video/mp4",
                            filename=f"{name}.mp4", content_disposition_type="inline")

    @app.post("/api/teams/propose", dependencies=guard)
    async def propose_team(body: dict = Body(...)):
        """Team builder (M9): one message in, a proposed team out. Nothing is saved."""
        goal = str(body.get("goal", "")).strip()
        if not goal:
            raise HTTPException(400, "Describe the team first")
        try:
            if mgr.fake_mode:
                await asyncio.sleep(mgr.fake_delay)
                return {**builder.clean_proposal(fake.demo_proposal(goal), mgr.catalog), "cost_usd": 0.0}
            return await builder.propose(goal, mgr.catalog, runner=mgr.runner)
        except ValueError as e:
            raise HTTPException(422, f"Couldn't design a team: {e}. Your message is kept.")

    @app.get("/api/teams", dependencies=guard)
    async def list_teams():
        return [team_out(t) for t in store.list()]

    @app.post("/api/teams", dependencies=guard, status_code=201)
    async def create_team(body: dict = Body(...)):
        return team_out(store.create(body, catalog_ids()))

    @app.get("/api/teams/{team_id}", dependencies=guard)
    async def get_team(team_id: str):
        return team_out(store.get(team_id))

    @app.put("/api/teams/{team_id}", dependencies=guard)
    async def update_team(team_id: str, body: dict = Body(...)):
        return team_out(store.update(team_id, body, catalog_ids()))

    @app.delete("/api/teams/{team_id}", dependencies=guard, status_code=204)
    async def delete_team(team_id: str):
        if teams.active_run(team_id):
            raise TeamError(409, "Stop the team's run before deleting it")
        store.delete(team_id)
        return Response(status_code=204)

    @app.get("/api/teams/{team_id}/room", dependencies=guard)
    async def team_room(team_id: str, limit: int = 200):
        store.get(team_id)
        return {"items": room_items(store.events(team_id), teams.run_dirs(team_id), limit),
                "active_run": teams.active_run(team_id)}

    @app.post("/api/teams/{team_id}/messages", dependencies=guard, status_code=202)
    async def team_message(team_id: str, body: dict = Body(...)):
        return await teams.message(team_id, str(body.get("text", "")))

    @app.post("/api/hooks/{team_id}/{secret}", status_code=202)  # no login: the secret in the URL is the key
    async def team_hook(team_id: str, secret: str, request: Request):
        raw = (await request.body())[:65536].decode("utf-8", errors="replace")
        res = await teams.webhook(team_id, secret, raw)
        return {"ok": True, "run_id": res["run_id"]}

    @app.get("/api/status", dependencies=guard)
    async def status():
        return mgr.status()

    # ---- web app ----------------------------------------------------------------------

    if web_dist.is_dir():
        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = (web_dist / path).resolve()
            if path and f.is_file() and web_dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(web_dist / "index.html")

    return app
