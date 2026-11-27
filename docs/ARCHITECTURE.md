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
replay/                     NEW: static replay page for the portfolio
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
| `GET /api/status` | | widget shape, below |
| `GET /api/health` | | `{ok, auth_mode, version, catalog: [ids]}` |

Shapes:
```jsonc
// options (all optional; defaults shown)
{"allow_bash": false, "repo": "", "orchestrator_model": "sonnet", "worker_model": "sonnet",
 "pick_tier": true, "max_tier": "opus", "checker_model": "haiku", "max_cost": 5.0,
 "max_agents": 6, "max_assignments": 15, "max_attempts": 3, "max_steps": 25,
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
{"options": {...}, "agents": [{"name", "role", "tools", "model", "color_index", "status"}],
 "board": [{"task_id", "title", "agent", "status", "attempts", "done_when", "feedback", "replaces", "replaced_by"}],
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
| `run_started` | `task, title, options, workspace, repo, branch, parent_id, auth_mode` | first event |
| `playbook_chosen` | `id, title` | orchestrator read a playbook (section 9b) |
| `orchestrator_said` | `text` | orchestrator's text blocks |
| `nudge` | `round, pending` | engine pushed the orchestrator to continue; shown only in the raw log |
| `agent_created` | `name, role, tools, model, tier_reason, color_index` | `tools` are catalog ids. `model` is the agent's tier (haiku, sonnet, opus) |
| `task_assigned` | `task_id, title, agent, task, done_when, replaces, tier, tier_reason, checks, checks_only` | `tier` is the task's model, from the task or its agent. `checks` are labels of cheap checks (section 9c) |
| `attempt_started` | `task_id, attempt, tier` | `tier` goes up one step after a failed attempt, once (M7) |
| `worker_activity` | `task_id, agent, tool, summary` | `summary` max 80 chars, e.g. "reading research/dana.md" |
| `file_written` | `task_id, agent, path, size` | path relative to the workspace |
| `checker_started` | `task_id, attempt` | |
| `attempt_failed` | `task_id, attempt, reason, short, checked_by, checks?` | `short` max 6 words. `checked_by`: `model`, `checks` or `worker` (it errored). `checks`: `[{check, passed, detail}]` |
| `task_passed` | `task_id, attempt, reason, short, checked_by, checks?` | as `attempt_failed` |
| `task_failed` | `task_id, attempts` | |
| `task_replaced` | `task_id, by` | |
| `approval_requested` | `approval_id, task_id, agent, tool, catalog_id, preview` | `preview` is a redacted summary of the tool input |
| `approval_resolved` | `approval_id, decision` | `approved`, `denied`, or `expired` |
| `usage` | `cost_usd, delta_usd, model_calls, turns, assignments` | totals after this change |
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
- **claude.ai connectors (status):** not verified yet; it needs your real Claude login (task 1.13).
  Until then Gmail and Google Calendar ship as `kind: "mcp"` entries that read their URL and token from
  `.env` (`GMAIL_MCP_URL`, `GMAIL_MCP_TOKEN`, `GCAL_MCP_URL`, `GCAL_MCP_TOKEN`). Without those they show
  as "not set up" and the orchestrator is not offered them.
- **Plugins:** every folder in `plugins/` with `.claude-plugin/plugin.json` becomes `plugin.<name>`.
- **Picking per run:** the new-run Options panel lists non-builtin entries as chips (from
  `GET /api/catalog`). The chosen ids go in `options.catalog`. Builtins are always available.
- The orchestrator prompt lists each enabled entry as `id: description (risk)`. The `create_agent`
  tool schema uses the enabled ids as its enum.
- `options.catalog` on a run can narrow the catalog for that run.

## 9b. Playbooks
Inspired by Lauren Tan's pstack (`/poteto-mode` routes work to a playbook).
- One markdown file per playbook in `orchestra/playbooks/`, front matter `id`, `title`, `when`.
  Body: steps, suggested roles and catalog tools, done-when templates, pitfalls.
- Shipped: `research-report`, `build-with-tests`, `repo-change`, `writing`, `general`.
- The orchestrator prompt lists every playbook's summary. Its first tool call is
  `read_playbook(id)`, which returns the full text and logs `playbook_chosen`.
- `options.playbook` (`"auto"` by default) lets you force one from the Options panel.
- Playbooks give hints, not fixed roles: the orchestrator still invents the agents.
- When a kind of run keeps failing the same way, fix the playbook's pitfalls, not only the prompt.

## 9c. Cheap checks (M7)
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
