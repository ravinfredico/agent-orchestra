# ChaCha PA: architecture

## 1. Overview
```
Browser (React app)                        Phone widget / ntfy app
   │  REST + SSE (same origin)                 │ GET /api/status      ▲ push
   ▼                                           ▼                      │
FastAPI server (server/)  ──────────────────────────────────────── notify.py ──► ntfy
   │  RunManager: one asyncio task per run, event bus per run
   ▼
Engine (orchestra/)  orchestrator → create_agent / assign_task → worker + checker
   │  Claude Agent SDK (query / ClaudeSDKClient)
   ▼
Claude Code CLI  ──►  Claude (Pro plan login, or API key)
   │  tools: built-ins, MCP servers (browser…), plugins, connectors
   ▼
runs/<id>/  meta.json · log.jsonl · board.json · final.md · workspace/      runs/index.db (SQLite)
```

Principles:
- **Files are the truth.** `log.jsonl` holds every event. Everything else, the SQLite index and the
  browser state included, can be rebuilt from it.
- **One event stream.** The CLI, the server, the replay page and the tests all use the same events.
- **The engine stays usable from the CLI.** `python main.py "task"` keeps working.

## 2. Stack
| Layer | Choice |
|---|---|
| Engine | Python 3.10+, Claude Agent SDK (`claude-agent-sdk`) |
| Server | FastAPI + uvicorn, `sse-starlette` for SSE, stdlib `sqlite3` (with a lock) for the index |
| Frontend | React 19 + Vite + TypeScript, React Router 7, no CSS framework (CSS variables from DESIGN.md tokens), Geist via `@fontsource-variable` |
| Live updates | Server-Sent Events with `Last-Event-ID` replay |
| Storage | Files under `runs/`, plus `runs/index.db` (SQLite with FTS5) |
| Tests | pytest (engine and server, offline with a fake runner), FastAPI TestClient, Vitest + Testing Library |
| Notifications | ntfy over HTTP |
| Hosting (later) | Cloudflare Tunnel + Cloudflare Access in front of the server on 127.0.0.1 |

## 3. Repository layout (target)
```
main.py                     CLI (unchanged usage)
orchestra/                  engine
  config.py                 Budget, Config, model defaults
  catalog.py                NEW: tool catalog loader → SDK options per agent
  prompts.py                orchestrator + checker prompts and schemas
  runner.py                 run_agent(): one agent via the SDK, forwards activity
  tools.py                  create_agent / assign_task / view_board / finish
  orchestrator.py           create_run() + execute_run(): the outer loop
  state.py                  RunState, events, listeners
  approvals.py              NEW: pending approvals, can_use_tool callback
  gitsafe.py                --repo safety
server/
  app.py                    FastAPI app, routes, SSE, static files
  runs.py                   RunManager: start, stop, continue, follow-up, recover
  summary.py                folds a run's log.jsonl into RunSummary / RunDetail
  index.py                  SQLite index: upsert, search, rebuild
  auth.py                   APP_TOKEN cookie/bearer check, host guard
  notify.py                 ntfy (M5)
orchestra/fake.py           scripted runner + client: offline tests and `python -m server --fake`
web/                        NEW: React app (Vite). Builds to web/dist
replay/                     static replay page: README; build output in replay/dist (web/src/replay is the source)
widgets/                    NEW: scriptable.js (iPhone), android-kwgt.md
tools.catalog.json          NEW: the tool catalog
tests/                      pytest; web/src/**/*.test.tsx for Vitest
```

## 4. Process model
- **RunManager** keeps `runs: dict[run_id, RunHandle]`. A `RunHandle` holds the `asyncio.Task`, the
  `RunState`, and the subscriber queues for SSE.
- **Start:** `create_run()` makes the run folder, `meta.json` and the state, and returns the id
  immediately. Then `execute_run()` is scheduled as a background task. `POST /api/runs` answers
  before any model call happens.
- **Several runs at once:** each run has its own folder and workspace. Two runs on the same repo at
  the same time are refused, because a git branch checkout is global to the repo.
- **Stop:** `task.cancel()`. `execute_run()` catches `CancelledError`, logs `run_stopped`, saves the
  board, and exits. The SDK subprocesses are closed by their context managers.
- **Crash:** any other exception is caught, classified (section 8), logged as `run_failed`, and saved.
- **Server restart:** on startup, every run whose `log.jsonl` has no terminal event gets
  `run_interrupted` appended, and the index is updated.
- **Closing the browser** does nothing to the run. SSE subscribers come and go.

## 5. Engine refactors
These are the changes to today's code, in the order M1 does them.

| # | File | Change |
|---|---|---|
| R1 | `state.py` | `RunState.log()` writes the envelope `{seq, run_id, t, type, ...}` to `log.jsonl`, then calls listeners (`add_listener(fn)`). Pretty ANSI printing moves into a CLI listener added by `main.py` only. Event names follow section 7 (`start` becomes `run_started`, `orchestrator` becomes `orchestrator_said`, `budget` becomes `budget_exhausted`). |
| R2 | `state.py` | `record_usage()` logs a `usage` event with totals and the delta. |
| R3 | `state.py` | Run id `%Y%m%d-%H%M%S-xxxxxx` (6 random hex). `RunState` stores `repo`, `branch`, `parent_id`, `auth_mode`, and writes `meta.json`. |
| R4 | `tools.py` | `assign_task` logs `attempt_started` before the worker and `checker_started` before the checker. |
| R5 | `tools.py`, `prompts.py` | `assign_task` takes a required `title` (2 to 4 words). The orchestrator prompt asks for it. |
| R6 | `prompts.py`, `tools.py` | The checker schema gets `short` (max 6 words, for the card). `attempt_failed` carries `reason` and `short`. |
| R7 | `runner.py` | `run_agent(..., on_event=None)`. For each `ToolUseBlock` in an `AssistantMessage` it calls `on_event("worker_activity", tool, summary)`. Write and Edit inputs also give `file_written`. After each attempt, a workspace scan catches files made through Bash. |
| R8 | `tools.py` | `create_agent` validates tool ids against the catalog (not the fixed registry), stores `color_index` (creation order), logs it. No role templates: the orchestrator writes any role. |
| R9 | `catalog.py` | Loads `tools.catalog.json` and turns a list of catalog ids into SDK options: `tools`, `allowed_tools`, `mcp_servers`, `plugins`, plus the set of outward tool names. See section 9. |
| R10 | `approvals.py`, `runner.py` | Agents with outward tools get a `can_use_tool` callback. It logs `approval_requested`, waits for a decision, then logs `approval_resolved`. See section 10. |
| R11 | `runner.py`, `config.py` | When shell is allowed, agents get `sandbox={"enabled": True, "allowUnsandboxedCommands": False, "network": {"allowedDomains": [...]}}`. Each agent also gets a private scratch folder `workspace/.agents/<name>/`. |
| R12 | `orchestrator.py` | Split `run()` into `create_run(task, config, ...) -> RunState` and `execute_run(state)`. `execute_run` handles cancel and crashes. `run()` stays as a wrapper for the CLI. |
| R13 | `gitsafe.py` | `prepare_repo()` returns the branch, and `RunState` stores it. A `REPOS_ROOT` allowlist check applies when set. |
| R14 | `orchestrator.py` | `continue_from(parent_id, extra_budget)` and `follow_up(parent_id, task)` seed the new run (section 11). |
| R15 | `server/auth.py` | `auth_mode()`: `"api_key"` if `ANTHROPIC_API_KEY` is set, else `"plan"`. Logged in `run_started`. |

Kept as is: the inner retry loop, `finish` refusing while tasks are unfinished, `replaces`, the budget
checks, workers never creating agents, and the orchestrator having no built-in tools.

## 6. HTTP API
All JSON. All routes need auth when a token is configured (section 13).

| Method and path | Request | Response |
|---|---|---|
| `POST /api/runs` | `{task, options, parent?: {run_id, mode: "continue" \| "follow_up"}}` | `201 {id, status: "running", created_at}` |
| `GET /api/runs` | query `q`, `status`, `repo` (bool), `limit` (default 50), `before` (cursor) | `{runs: [RunSummary], next}` |
| `GET /api/runs/{id}` | | `RunDetail` |
| `GET /api/runs/{id}/events` | header `Last-Event-ID` or query `after` | SSE stream (section 7) |
| `GET /api/runs/{id}/files` | | `[{path, size, mtime, agent, versions}]` |
| `GET /api/runs/{id}/files/{path}` | | raw text, `Content-Type` by extension, max 2 MB, path checked to stay inside the workspace |
| `GET /api/runs/{id}/zip` | | `application/zip` of the workspace (skips `.agents/` and `.git/`) |
| `POST /api/runs/{id}/stop` | | `202 {status: "stopping"}` |
| `POST /api/runs/{id}/approvals/{approval_id}` | `{decision: "approve" \| "deny"}` | `200 {ok: true}` |
| `POST /api/runs/{id}/continue` | `{extra_budget_usd}` | `201 {id}` (a new run) |
| `DELETE /api/runs/{id}` | | `204`. Refused with `409` while running. |
| `GET /api/catalog` | | `[CatalogEntry]` without secrets |
| `GET /api/playbooks` | | `[{id, title, when}]` |
| `POST /api/runs/{id}/messages` | `{text}` | `202`. Steering: your message reaches the orchestrator at its next step. `409` if not running |
| `GET /api/teams` | | `[Team + active_run]` |
| `POST /api/teams` | `Team` fields | `201 Team`. `400` with a plain reason (unknown tool, bad cron, unknown time zone) |
| `GET/PUT/DELETE /api/teams/{id}` | `PUT`: any Team fields, `memory` replaces memory.md | `Team` / `204` (`409` while its run is going) |
| `GET /api/teams/{id}/room` | query `limit` (200) | `{items: [RoomItem], active_run}` |
| `POST /api/teams/{id}/messages` | `{text}` | `202 {run_id, steered}`: starts a run, or steers the running one |
| `POST /api/hooks/{team_id}/{secret}` | any body (64 KB max) | `202 {run_id}`. No login: the secret in the URL is the key. `404` if wrong or the hook is off |
| `GET /api/status` | | widget shape, below |
| `GET /api/health` | | `{ok, auth_mode, version, catalog: [ids]}` |

Shapes:
```jsonc
// options (all optional; defaults shown)
{"allow_bash": false, "repo": "", "orchestrator_model": "sonnet", "worker_model": "sonnet",
 "pick_tier": true, "max_tier": "opus", "checker_model": "haiku", "max_cost": 5.0,
 "max_agents": 6, "max_assignments": 15, "max_attempts": 3, "max_steps": 25, "max_parallel": 3,
 "catalog": ["*"], "allowed_domains": []}
// worker_model: the default tier when the orchestrator names none (pick_tier: true),
//   or the tier every worker uses (pick_tier: false).
// max_tier: highest tier a pick or a step-up may reach. max_steps: tool-use turns per try.
// The web app's Cheap preset (web/src/presets.ts): worker_model haiku, max_tier sonnet,
//   max_cost 1, max_attempts 2, max_steps 15, max_assignments 8.

// RunSummary
{"id": "20261123-091402-a3f1c2", "title": "Indonesian e-wallets report", "task": "...",
 "status": "running|finished|gave_up|failed|stopped|interrupted", "needs_approval": false,
 "created_at": 1795425000.1, "ended_at": null, "duration_s": 24, "cost_usd": 0.74,
 "agents": [{"name": "researcher", "color_index": 0}], "tasks_total": 2, "tasks_passed": 1,
 "repo": null, "branch": null, "parent_id": null}

// RunDetail = RunSummary + 
{"options": {...}, "agents": [{"name", "role", "tools", "model", "tier_reason", "color_index", "status"}],
 "board": [{"task_id", "title", "agent", "status", "attempts", "done_when", "feedback", "replaces", "replaced_by",
            "tier", "tier_reason", "checks", "checks_only", "depends_on", "owns",
            "history": [{"attempt", "tier", "passed", "reason", "short", "checked_by", "checks"}]}],
 "usage": {"by_agent": {"<name>": {"cost_usd", "calls", "role", "models", "tasks"}},
           "by_model": {"<model>": {"cost_usd", "calls"}}},
 "files": [...], "final": "...", "error": null, "pending_approvals": [...], "last_seq": 57}

// GET /api/status (for widgets)
{"running": [{"id", "title", "status", "elapsed_s", "cost_usd", "agents", "needs_approval"}],
 "last": {"id", "title", "status", "ended_at"}}
```

The run `title` is short: the orchestrator's first task-independent summary if present, else the
first 6 words of the task.

## 7. Live event schema
Every line in `log.jsonl` and every SSE message is one event:
```json
{"seq": 12, "run_id": "20261123-091402-a3f1c2", "t": 1795425012.4, "type": "task_assigned", "...": "fields"}
```
- `seq` starts at 1 per run and never skips. It is the SSE `id`.
- SSE frame: `id: <seq>`, `event: <type>`, `data: <json>`. Comment keepalive every 15 s.
- On connect, the server replays every event with `seq` greater than `Last-Event-ID` (or `after`)
  from `log.jsonl`, then streams live. After a terminal event it sends `event: end` and closes.

| Type | Fields | Notes |
|---|---|---|
| `run_started` | `task, title, options, workspace, repo, branch, parent_id, auth_mode, team_id, team_name, trigger` | first event. `trigger`: `{kind: manual \| message \| schedule \| webhook, ...}` (M8) |
| `user_message` | `text` | you wrote during the run (steering, M8). The orchestrator gets it with its next tool result |
| `playbook_chosen` | `id, title` | orchestrator read a playbook (section 9b) |
| `orchestrator_said` | `text` | orchestrator's text blocks |
| `nudge` | `round, pending` | engine pushed the orchestrator to continue; shown only in the raw log |
| `agent_created` | `name, role, tools, model, tier_reason, color_index` | `tools` are catalog ids. `model` is the agent's tier (haiku, sonnet, opus) |
| `task_assigned` | `task_id, title, agent, task, done_when, replaces, tier, tier_reason, checks, checks_only, depends_on, owns` | `tier` is the task's model, from the task or its agent. `checks` are labels of cheap checks (section 9d) |
| `attempt_started` | `task_id, attempt, tier` | `tier` goes up one step after a failed attempt, once (M7) |
| `worker_activity` | `task_id, agent, tool, summary` | `summary` max 80 chars, e.g. "reading research/dana.md" |
| `file_written` | `task_id, agent, path, size` | path relative to the workspace |
| `checker_started` | `task_id, attempt` | |
| `attempt_failed` | `task_id, attempt, reason, short, checked_by, checks?` | `short` max 6 words. `checked_by`: `model`, `checks` or `worker` (it errored). `checks`: `[{check, passed, detail}]` |
| `task_passed` | `task_id, attempt, reason, short, checked_by, checks?` | as `attempt_failed` |
| `task_failed` | `task_id, attempts, reason?` | `attempts: 0` with `reason`: never started (a dependency failed, or out of budget). It can be replaced like any failed task |
| `task_replaced` | `task_id, by` | |
| `approval_requested` | `approval_id, task_id, agent, tool, catalog_id, preview` | `preview` is a redacted summary of the tool input |
| `approval_resolved` | `approval_id, decision` | `approved`, `denied`, or `expired` |
| `usage` | `cost_usd, delta_usd, model_calls, turns, assignments, agent, role, model, task_id` | totals after this change. `agent`, `role` (orchestrator, worker, checker), `model` and `task_id` say who spent `delta_usd` (M7). The orchestrator's usage lands when its turn ends |
| `budget_exhausted` | `reason` | |
| `finished` | `give_up, result` | terminal. `give_up` true means out of budget |
| `run_failed` | `error, kind, hint` | terminal. `kind`: `auth`, `limit`, `crash` |
| `run_stopped` | | terminal |
| `run_interrupted` | | terminal, written at server start |

The frontend keeps one reducer that applies these events to a run state (agents, board, files,
usage, status, approvals). The replay page and the tests use the same reducer.

## 8. Errors and crash kinds
| Kind | Detected by | UI copy |
|---|---|---|
| `auth` | CLI exit with "not logged in", 401, "invalid api key" | "Your Claude login expired…" with fix steps |
| `limit` | "usage limit", "rate limit", 429 | "You've hit your plan's usage limit. It resets at <time>." |
| `crash` | anything else | "The run crashed" + technical details |

A worker error inside an attempt is not a crash. It is fed back to the inner loop as feedback, as today.

## 9. Tool catalog
The orchestrator can only give agents tools from the catalog. `tools.catalog.json`:
```jsonc
[
  {"id": "files.read",  "kind": "builtin", "tools": ["Read", "Glob", "Grep"], "risk": "read",
   "description": "Read and search files in the workspace"},
  {"id": "files.write", "kind": "builtin", "tools": ["Write", "Edit"], "risk": "write",
   "description": "Create and edit files in the workspace"},
  {"id": "web",         "kind": "builtin", "tools": ["WebSearch", "WebFetch"], "risk": "read",
   "description": "Search the web and read pages"},
  {"id": "shell",       "kind": "builtin", "tools": ["Bash"], "risk": "shell", "requires": "allow_bash",
   "description": "Run commands in the sandbox (code, tests, installs)"},
  {"id": "browser",     "kind": "mcp", "risk": "read",
   "server": {"type": "stdio", "command": "npx", "args": ["@playwright/mcp@latest", "--headless"]},
   "description": "Open and use real web pages: click, type, read, screenshot"},
  {"id": "gmail",       "kind": "mcp", "risk": "outward", "enabled": false,
   "server": {"type": "http", "url": "https://…", "headers": {"Authorization": "${GMAIL_MCP_TOKEN}"}},
   "outward_tools": ["send_message", "create_draft"],
   "description": "Read and send email"},
  {"id": "my-plugin",   "kind": "plugin", "path": "./plugins/my-plugin", "risk": "write",
   "description": "Example local Claude Code plugin"}
]
```
- `risk` is one of `read`, `write`, `shell` or `outward`. An outward entry can list only some of its
  tools as `outward_tools`; the rest run freely.
- `${VAR}` values come from the environment (`.env`), never from the file. Secrets never reach the
  browser.
- **Mapping to the SDK** (`catalog.py`):
  - builtin ids add to `tools` and `allowed_tools`
  - mcp ids add `mcp_servers[id] = server`, and the server's tools go in `allowed_tools`, except
    outward ones
  - plugin ids add to `plugins`
- **claude.ai connectors (`orchestra/connectors.py`, F29 to F30):** Claude Code's docs say sessions
  signed in with a claude.ai account, Agent SDK runs included, load the account's claude.ai connectors
  automatically; tools are named `mcp__claude_ai_<Name>__<tool>`. So:
  - Discovery: `claude mcp list` (health check, no model call), parsed for `claude.ai <Name>` lines,
    cached 5 minutes. Each becomes `kind: "connector"`, id `connector.<name>`, `risk: outward`, with
    status: connected, or "not set up" with the sign-in fix.
  - The server adds them on every catalog read (`RunManager.catalog`); the CLI adds them per run.
    Demo mode shows sample Figma, Notion and Slack connectors.
  - Per agent (`Catalog.toolset`): chosen connectors go in `read_only_servers` (read name patterns
    run freely, everything else goes through the approval callback). Connectors not chosen go in
    `disallowed_tools`. An agent with none, the orchestrator and the checker run with
    `ENABLE_CLAUDEAI_MCP_SERVERS=false`, so connectors aren't loaded at all.
  - The approval callback denies any tool the agent wasn't given (`Toolset.owns`).
  - Not yet confirmed on a real login (task 1.13). The `.env` Gmail and Calendar MCP entries stay as
    a fallback.
- **Plugins:** every folder in `plugins/` with `.claude-plugin/plugin.json` becomes `plugin.<name>`.
- **App variables:** `${ORCHESTRA_ROOT}` (this repo) and `${PYTHON}` (the running Python) are filled in
  by the app, so entries can start servers that ship in `mcp_servers/` on any OS.
- **Video-team entries (2026-11-27):**
  - `elevenlabs`: `uvx elevenlabs-mcp` with `ELEVENLABS_API_KEY`; files land in the workspace. Tools
    matching `*call*`, `*agent*`, `*phone*`, `*whatsapp*` are outward (calls and voice agents).
  - `tiktok`: `${PYTHON} ${ORCHESTRA_ROOT}/mcp_servers/tiktok.py` with `TIKTOK_ACCESS_TOKEN`, on TikTok's
    v2 APIs: `creator_info`, `list_videos`, `post_status` (read); `upload_draft`, `publish_video`
    (outward). Uploads go in one chunk up to 64 MB. `publish_video` is `SELF_ONLY` unless
    `TIKTOK_PRIVACY` or the call says otherwise, because unaudited apps can only post privately.
- **Picking per run:** the new-run Options panel lists non-builtin entries as chips (from
  `GET /api/catalog`). The chosen ids go in `options.catalog`. Builtins are always available.
- The orchestrator prompt lists each enabled entry as `id: description (risk)`. The `create_agent`
  tool schema uses the enabled ids as its enum.
- `options.catalog` on a run can narrow the catalog for that run.

## 9b. Playbooks
Inspired by Lauren Tan's pstack (`/poteto-mode` routes work to a playbook).
- One markdown file per playbook in `orchestra/playbooks/`, front matter `id`, `title`, `when`.
  Body: steps, suggested roles and catalog tools, done-when templates, pitfalls.
- Shipped: `research-report`, `build-with-tests`, `repo-change`, `writing`, `short-video`, `general`.
- The orchestrator prompt lists every playbook's summary. Its first tool call is
  `read_playbook(id)`, which returns the full text and logs `playbook_chosen`.
- `options.playbook` (`"auto"` by default) lets you force one from the Options panel.
- Playbooks give hints, not fixed roles: the orchestrator still invents the agents.
- When a kind of run keeps failing the same way, fix the playbook's pitfalls, not only the prompt.

## 9c. Parallel tasks (M7)
`assign_tasks({tasks: [...]})` takes several tasks, each with the `assign_task` fields plus:
- `depends_on`: task ids that must pass first, from the same batch or already done.
- `owns`: files or folders only this task writes while it runs.

Rules:
- The whole batch is checked before anything starts: unknown agents or dependencies, loops, two
  tasks that may run at once owning the same path, a path owned by a running task, or more tasks
  than assignments left. Any problem refuses the batch and registers nothing.
- All tasks are logged as `task_assigned` up front (queued cards). A task starts when its
  dependencies have passed, its agent is free (one task per agent at a time), and fewer than
  `max_parallel` (default 3) are running.
- A task whose dependency did not pass is never started: `task_failed` with `attempts: 0` and a
  `reason`. The orchestrator replaces it like any failed task.
- With `owns`, the post-attempt file scan only reports changes inside the owned paths, so parallel
  tasks don't claim each other's files.
- The call returns when every task has ended: "N of M tasks passed", then each result.
- Stop cancels the orchestrator's turn; `assign_tasks` cancels every running task before it returns.

## 9d. Cheap checks (M7)
`orchestra/checks.py`. A task can carry `checks`, run after each worker attempt and before the
model checker, with no model call:

| Type | Fields | Passes when |
|---|---|---|
| `file_exists` | `path` | the file exists in the workspace |
| `file_count` | `glob, min` | at least `min` files match |
| `contains` | `path, text` | the file contains the text (any case) |
| `min_words` | `path, min` | the file has at least `min` words |
| `command` | `run` | the command exits 0 within 120 s. Only when shell is on for the run |

- A failing check fails the attempt with a reason for the worker; the model checker is skipped.
- Passing checks are listed in the checker prompt so it doesn't redo them.
- `checks_only: true` passes the task on passing checks, with no model checker.
- Paths and globs can't leave the workspace. Commands run in the workspace, not in the SDK sandbox,
  which is why they need shell on.

## 9e. Teams, triggers and steering (M8)
`server/teams.py`. A team is a folder `teams/<id>/` next to `runs/`:
- `team.json`: `name, goal, members [{name, role, system_prompt, tools, tier}], schedule [{cron, task}],
  timezone, enabled, hook {enabled, task, secret}, options` (run options, Cheap preset by default).
- `memory.md`: your notes, plus a "Past runs" list. After each team run the app adds
  `- <date> · <title> · <status>: <first 300 chars of the result>`. Past 8000 chars the oldest runs drop off.
- `events.jsonl`: team-level events, today only `trigger_skipped`.

A team run is a normal verified run with `team` and `trigger` set:
- Its members are created (logged as `agent_created`) before the orchestrator starts.
- The first prompt starts with the team's name, goal, members and memory (`prompts.team_context`).
- `meta.json` and `run_started` carry `team_id` and `trigger`.

Triggers (the only way a team spends usage; one run per team at a time):
| Trigger | Starts | If the team is busy |
|---|---|---|
| Room message | a run with your message as the task | the message steers the running run |
| Schedule slot | cron `minute hour day month weekday` in the team's time zone (empty: this machine's). The server checks every 20 s and fires each slot once per minute | skipped, logged as `trigger_skipped`, shown in the room |
| Webhook | a run with the hook's task plus the posted data | the data steers the running run |

- Pause (`enabled: false`) stops schedule slots. Messages and the webhook still work.
- Slots missed while the server was off are not caught up.
- No daily cap (your decision, 2026-11-27). Teams use the Cheap preset unless you change it.

Steering (`RunState.steer`): your message is logged as `user_message` and queued. Every orchestra
tool result carries queued messages to the orchestrator. `finish` is refused while any are unread,
so it can't end the run without seeing what you said. A message that arrives after `finish` was
accepted starts the team's next run. Long `assign_tasks` batches delay delivery until they return.

The room (`room_items`) is folded from the team's run logs plus `events.jsonl`: your messages (the
task of a message-started run and every `user_message`), orchestrator replies, hand-offs
(`task_assigned`: orchestrator → agent), checker results, final results, and system lines.
Approval requests show in the room with Approve and Deny (they call the run's approvals endpoint).

## 9f. Replay page (M6)
- Source: `web/replay.html` and `web/src/replay/` (`Replay.tsx` player, `clock.ts` pacing and scrub,
  `run.json` the recorded run, written by `scripts/make_fixtures.py` from the demo scenario).
- It folds the log with the app's reducer and renders the app's thread, task cards and rail, inside a
  `MemoryRouter` so no link leaves the page. No fetch, no SSE, no server.
- Pacing ignores real gaps: each event holds for a fixed time by type (`holdAfter`), at 1×, 2× or 4×.
  A position slider jumps to any event. The end shows "Replay finished" with the final result.
- `scrub()` nulls `workspace`, `repo`, `branch`, and replaces machine paths and token-looking strings.
- Build: `npm run build:replay` → `replay/dist/` (relative base, so it works under `/<repo>/`).
- Publish: `.github/workflows/replay-pages.yml` (tests, build, deploy to Pages) on `main` or by hand.

## 10. Approvals for outward tools
- Servers with outward tools are left out of `allowed_tools`, so the CLI asks the SDK's `can_use_tool`
  callback before each of their calls. The callback lets non-outward tools straight through.
- The callback (`approvals.py`):
  1. creates `approval_id` and an `asyncio.Future`
  2. logs `approval_requested` with a redacted preview of the input
  3. sends an ntfy push
  4. waits on the future
- `POST /api/runs/{id}/approvals/{approval_id}` resolves the future.
  - Approve returns allow with the original input.
  - Deny returns deny with the message "Denied by the user. Continue without this action."
- Stopping a run resolves every pending approval as `expired`.
- In CLI mode with no server, outward tools are denied with a clear message.
- Checked in the SDK source: `can_use_tool` works with plain string prompts (stdin stays open while
  callbacks are pending). Agents with a callback use `permission_mode="default"`, others `"dontAsk"`.

## 11. Continue and follow-up
- **Continue** (from `gave_up`, `stopped`, `failed` or `interrupted`):
  - A new run with `parent_id` and a budget of `extra_budget_usd`.
  - The workspace is copied from the parent. In repo mode it reuses the same branch.
  - The orchestrator's first prompt includes the parent's board (done and unfinished tasks with their
    last feedback) and `final.md`.
- **Follow-up** (from `finished`):
  - A new run with `parent_id`, a fresh budget, and a copy of the parent's workspace.
  - The first prompt is your new task plus the parent's `final.md`.
- History shows the link both ways.

## 12. Persistence
```
runs/<id>/
  meta.json      task, title, options, parent_id, repo, branch, auth_mode, created_at
  log.jsonl      every event (the source of truth)
  board.json     agents, board, usage (rewritten on change, as today)
  final.md       final result text
  workspace/     files the agents made (absent in repo mode, where the repo is the workspace)
runs/index.db    SQLite: runs table + FTS5 over task and title
```
- The index is updated on `run_started`, every `usage` (cost only), and terminal events.
- `python -m server.index --rebuild` rebuilds it from `runs/*/log.jsonl`.
- Delete removes the folder, then the index row.
- `runs/` is in `.gitignore`.

## 13. Security
**Sign-in:** the app contains no login code. It never asks for, reads, stores or sends Claude
credentials. The SDK starts the installed Claude Code, which uses its own sign-in (`auth_mode()` only
checks whether `ANTHROPIC_API_KEY` is set, to label the mode). Plan login is for personal use; see
README "Sign-in and terms".

- uvicorn binds to `127.0.0.1` only. The server refuses to start on any other host unless
  `APP_TOKEN` is set.
- **Auth:** when `APP_TOKEN` is set, `POST /api/login` with the token sets an HttpOnly, SameSite=Strict
  cookie. Every route checks the cookie or `Authorization: Bearer`. A cookie is needed because
  EventSource can't send headers.
- **Hosted:**
  - Cloudflare Tunnel (`cloudflared`) forwards to `127.0.0.1:8000`.
  - A Cloudflare Access policy allows only your email.
  - Widgets use an Access service token (`CF-Access-Client-Id` / `CF-Access-Client-Secret`) plus the
    app token.
- **Files:** every path is resolved and checked to stay inside the run's workspace.
- **Repo mode:** clean tree, new branch. `REPOS_ROOT` restricts repos when set, which is required
  when hosted.
- **Shell:** off by default. When on, the SDK sandbox blocks unsandboxed commands and limits network
  to `allowed_domains` (plus package registries if you tick them).
- **Outward tools:** always need approval.
- **Secrets** live in `.env`, which is ignored by git. The catalog file only holds `${VAR}` references.
- **Billing guard:** in plan mode the sidebar shows "Pro plan". If `ANTHROPIC_API_KEY` appears, the
  indicator changes to "API key · billed" and `run_started` records it.

## 14. Notifications and widgets
- `server/notify.py` publishes JSON to `${NTFY_URL}` (topic in the body, so non-English titles
  survive) with a title, a short message, a click URL (`${PUBLIC_URL}/runs/<id>`), tags and a
  priority. `NTFY_TOKEN` is sent as a bearer token when set. Pushes go out on a background thread;
  a failed push is printed and never affects the run.
- `.env` is loaded at startup by `orchestra/envfile.py` (server and CLI). Shell variables win, and
  `ANTHROPIC_API_KEY` is never loaded from the file.
- It sends on these events, and is off when `NTFY_URL` is unset:
  - `finished`
  - `budget_exhausted` followed by `finished` with `give_up`
  - `run_failed`
  - `approval_requested` (high priority)
- `widgets/scriptable.js`: an iPhone home-screen widget. It fetches `/api/status` and shows the
  running task, team count, usage and last result. iOS decides the refresh rate, usually every few
  minutes.
- `widgets/android-kwgt.md`: the same with KWGT. KWGT's web fetch can't send headers, so Tasker
  makes the authenticated request and passes the values to KWGT. Tokens never go in a URL.

## 15. Frontend
- Routes:
  - `/` new run
  - `/runs/:id` run
  - `/runs/:id/files/*` files
  - `/history`
- `useRunEvents(id)`: an EventSource hook that feeds the reducer from section 7. It reconnects with
  the last seq automatically.
- Components mirror DESIGN.md: `Character`, `TaskCard`, `ApprovalCard`, `OutcomeCard`, `RunBar`,
  `Composer`, `Sidebar`, `Rail`, `FileViewer`. Tokens are CSS variables per theme.
- **Live announcements:** a single `<Announcer>` with `role="status"`, fed by the reducer's list of
  announceable events.
- **Build:** `npm run build` writes `web/dist`. FastAPI serves it with an SPA fallback.
- **Dev:** Vite on :5173 proxies `/api` to :8000.

## 16. From localhost to private hosting
1. **Local (v1):** `python -m server` on your laptop, open `http://127.0.0.1:8000`. Plan login.
2. **Always-on:** run the same command as a systemd service (Linux) or launchd agent (macOS).
   - Your own machine: plan login stays on your device.
   - VPS: set `ANTHROPIC_API_KEY`. The app works the same and shows "API key · billed".
3. **Reach it from anywhere:**
   - Set `APP_TOKEN`.
   - Install `cloudflared`, create a tunnel to `127.0.0.1:8000`, and add a Cloudflare Access app
     for your email.
4. **Phone:** add to home screen, subscribe to the ntfy topic, install the widget script.

## 17. Later
| Feature | Plan |
|---|---|
| Steering | The orchestrator already runs in a `ClaudeSDKClient` session. A message you type is queued and sent with `client.query()` when the current turn ends, or after `client.interrupt()` if urgent. New events: `user_said`. |
| Docker per agent | Each agent runs its CLI inside its own container with the run's `workspace/` mounted at `/workspace`. Through `cli_path` pointing at a wrapper, or by running the agent loop in the container. Network per container from `allowed_domains`. |
| OpenRouter models | An agent with a non-Claude model gets `env={"ANTHROPIC_BASE_URL": <LiteLLM gateway>}`. LiteLLM routes to OpenRouter with `OPENROUTER_API_KEY`. Billed by OpenRouter. The `model` field accepts `openrouter/<model>`. |
| Repo diff | `GET /api/runs/{id}/diff` returns `git diff <base>...<branch>`. Shown in the file viewer. |
