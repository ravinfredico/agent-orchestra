# ChaCha PA: implementation plan

Each task is small enough for one sitting. Each one lists what "done" means and the tests that
prove it.
- Engine and server tests are pytest and fully offline: they use the fake runner pattern in
  `tests/test_tools.py` and never call a model.
- Web tests use Vitest + Testing Library.
- Refactor ids (R1 to R15) point to `docs/ARCHITECTURE.md` section 5.

Rule for every task: `python -m pytest tests -q` passes before the commit, and the CLI still works.

## Progress
| Milestone | State |
|---|---|
| M1 Engine | Done offline (54 pytest tests). Open: 1.13 connectors check and 1.14 first live run, both need your Claude login. |
| M2 Server | Done (`tests/test_server.py`). |
| M3 App core | Done. Vitest reducer + component tests, Playwright screenshots reviewed at 1440 and 390 px. |
| M4 App complete | Done, except the manual screen reader pass in 4.6 and 4.7 (canvas additions). 4.6 automated part done: `npm run a11y` is clean. |
| Playbooks | Done: 5 playbooks, `read_playbook`, `playbook_chosen`, Options select (`tests/test_playbooks.py`). |
| M5 Phone extras | Done offline: 5.1 ntfy, 5.4 PWA, 5.2 iPhone widget (logic tested in `web/src/test/widget.test.ts`), 5.3 Android guide. Open: trying both widgets on real phones. |
| M6 | Not started. |
| M7 to M9 (after v1) | Planned 2026-11-27: parallel and cheaper, teams and schedules, team builder. PRD section 13. |

## M1: Engine events and capabilities
Goal: the engine emits the full event stream, can be cancelled, uses the tool catalog, asks for
approvals, and has run once for real.

| # | Task | Done when | Tests |
|---|---|---|---|
| 1.1 | Event envelope and listeners (R1) | Every `log()` writes `{seq, run_id, t, type, ...}`. `seq` starts at 1 and never skips. Listeners get each event. ANSI printing only happens through a CLI listener. | `test_events.py`: seq order, listener called once per event, no ANSI in `log.jsonl`, renamed event types |
| 1.2 | Usage event (R2) | `record_usage()` logs `usage` with totals and the delta. | usage totals match after 3 fake attempts |
| 1.3 | Run ids and meta (R3, R13) | Ids look like `YYYYmmdd-HHMMSS-xxxxxx`. Two runs in the same second differ. `meta.json` is written. The repo branch is stored. | unique ids over 50 quick creations, `meta.json` fields, `prepare_repo` returns the branch (extend `test_gitsafe.py`) |
| 1.4 | Attempt and checker events (R4) | `attempt_started` comes before each worker call and `checker_started` before each checker call. | event order for pass-first-try and pass-on-retry |
| 1.5 | Task title and short reason (R5, R6) | `assign_task` requires `title`. The checker schema has `short`. `attempt_failed` carries both reason and short. A missing title is rejected with a clear error. | title required, short carried, fallback when the checker omits short |
| 1.6 | Worker activity and file events (R7) | The runner reports each tool use as `worker_activity` with a summary of at most 80 chars. Write and Edit report `file_written`. A post-attempt scan reports files made through Bash. | fake runner emits tool uses, events follow, summary truncation, scan finds new files |
| 1.7 | Tool catalog (R8, R9) | `tools.catalog.json` loads. `create_agent` accepts only enabled catalog ids. Ids map to `tools`, `allowed_tools`, `mcp_servers` and `plugins`. `${VAR}` values resolve from the environment. `color_index` is set in creation order. `shell` is only offered when `allow_bash` is on. | `test_catalog.py`: mapping per kind, unknown id rejected, disabled entry hidden, env substitution, secrets never in `agent_created` |
| 1.8 | Browser in the catalog | The `browser` entry (Playwright MCP) is enabled by default. An agent given `browser` gets the MCP server config. | mapping test. A manual check that the browser tools appear in a real session. |
| 1.9 | Approvals (R10) | Outward tools go through `can_use_tool`: `approval_requested` is logged, the call waits, approve and deny both work, stop resolves pending ones as expired. In CLI mode outward tools are denied. | `test_approvals.py`: approve path, deny path, expiry on cancel (fake callback, no model) |
| 1.10 | Sandbox (R11) | With `allow_bash`, agents get the sandbox settings and a private `.agents/<name>/` folder. Without it, no Bash and no sandbox. | options built correctly in both cases |
| 1.11 | Split run, cancel, crash kinds (R12, R15) | `create_run()` returns at once. `execute_run()` logs `run_stopped` on cancel and `run_failed` with `kind` on errors. `auth_mode` is in `run_started`. `run()` still works for the CLI. | cancel mid-attempt gives `run_stopped` and a saved board, injected auth and limit errors map to the right kind, CLI smoke test with a fake runner |
| 1.12 | Continue and follow-up (R14) | `continue_from()` copies the workspace and puts the parent board and final text into the first prompt. `follow_up()` copies the workspace with a new task. `parent_id` is set. | files copied, prompt contains unfinished tasks, parent link |
| 1.13 | Verify claude.ai connectors | A short note in ARCHITECTURE.md section 9 says whether SDK sessions can reach your connectors, and which fallback is used. | manual check |
| 1.14 | **First live run (CLI)** | The e-wallet task runs end to end on your Pro plan. `log.jsonl` has the full event stream. Bugs found get fixed, with a test each. | manual (see "First manual end-to-end test" below) |

## M2: Server
Goal: everything the UI needs, tested without a browser or model.

| # | Task | Done when | Tests |
|---|---|---|---|
| 2.1 | App skeleton and health | `python -m server` serves `GET /api/health` on 127.0.0.1:8000 with `auth_mode`. It refuses a non-loopback host without `APP_TOKEN`. | TestClient: health shape, host guard |
| 2.2 | RunManager start | `POST /api/runs` returns 201 with an id before any model call. The run executes in the background. Several runs at once work. A second run on the same repo is refused with 409. | fake runner: 3 parallel runs finish, repo conflict |
| 2.3 | SSE events | `GET /api/runs/{id}/events` replays from `Last-Event-ID` or `after`, then streams live, then sends `end`. Keepalive every 15 s. | replay from 0 and from N, live events arrive, end after terminal |
| 2.4 | Run detail and list | `GET /api/runs/{id}` and `GET /api/runs` return the documented shapes. | shape tests, filters, cursor paging |
| 2.5 | SQLite index | The index is updated on start, usage and end. Search uses FTS. `--rebuild` recreates it from logs. | rebuild equals live index, search hits task words |
| 2.6 | Stop | `POST /stop` cancels within 5 s and gives `run_stopped`. | timing with a slow fake runner |
| 2.7 | Approvals endpoint | `POST /approvals/{id}` resolves the pending call. Unknown ids give 404. | approve and deny through HTTP |
| 2.8 | Files and zip | List, read (with a traversal guard and a 2 MB cap), zip (skips `.agents/` and `.git/`). | `../` rejected, zip contents |
| 2.9 | Delete, continue | DELETE removes the folder and index row (409 while running). `POST /continue` creates a linked run. | both paths |
| 2.10 | Recovery | On startup, runs without a terminal event get `run_interrupted`. | write a half log, start the app, check the event |
| 2.11 | Auth | With `APP_TOKEN`: login sets a cookie, routes need the cookie or a bearer token, SSE works with the cookie. | 401 without, 200 with |
| 2.12 | Status endpoint | `GET /api/status` returns running runs and the last result. | shape with 0, 1 and 2 running |

## M3: App core (React)
Goal: start a run and watch it live, matching screens 1 to 6 and 9 of the canvas.

| # | Task | Done when | Tests |
|---|---|---|---|
| 3.1 | Scaffold | `web/` with Vite + React + TS, tokens as CSS variables for dark and light, Geist fonts. FastAPI serves `web/dist` with an SPA fallback. The theme switch is remembered per browser. | Vitest runs. Build output is served. |
| 3.2 | Event reducer | One reducer turns events into run state: agents, board, files, usage, status, approvals, announcements. | Vitest: replay the 3 mock scenarios from the design phase, check the final state of each |
| 3.3 | `useRunEvents` | EventSource hook with reconnect from the last seq. | mock EventSource: reconnect resumes without duplicates |
| 3.4 | Character | All 6 moods and the accessories as an SVG component with a label. Motion per DESIGN.md section 4, with reduced motion respected. | renders every mood, aria-label, reduced-motion class |
| 3.5 | Sidebar, Rail, TaskCard | Match the canvas components and every TaskCard state. Cards open and close with keyboard. | each state renders its status line and dots, Enter and Escape |
| 3.6 | New run screen | Composer, options panel, suggestions. Start is disabled when empty. Cmd/Ctrl+Enter starts. | form posts the right options |
| 3.7 | Live run screen | Thread, joined lines, activity line, run bar, Stop with confirm. | renders from a replayed log. Stop calls the API after confirm. |
| 3.8 | Retry and replan | Failed card with checker lines, crossed-out replaced card. | from the retry scenario log |
| 3.9 | Approval card | Pending, approved, denied, expired. The run bar shows "Needs your approval". | approve and deny call the API |
| 3.10 | Outcome cards | Finished, out of budget (with Continue), crashed (per kind), stopped, interrupted. | one test per outcome |
| 3.11 | Announcer | One `role=status` region announces only the events listed in DESIGN.md section 8. | announces task_passed, ignores worker_activity |
| 3.12 | Plan-mode indicator | Sidebar shows the mode from `/api/health`. | both modes |

## M4: App complete
| # | Task | Done when | Tests |
|---|---|---|---|
| 4.1 | History page | Search, filters, grouping by day, team faces. | filter and search call the API with the right query |
| 4.2 | History actions | Rerun with edits (pre-filled form), zip download, delete with confirm. | each action |
| 4.3 | File viewer | List with author characters, markdown rendering, code view, Copy, Raw. | markdown table renders, code untouched |
| 4.4 | Follow-up and continue | Follow-up box on finished runs, Continue on out-of-budget, interrupted and stopped runs. Parent link shown. | API calls and the resulting navigation |
| 4.5 | Responsive and phone | The layouts in DESIGN.md section 6: rail panel, sidebar drawer, phone header, team strip, run bar, bottom sheets. | Playwright screenshots at 390, 900 and 1440 px (manual review) |
| 4.6 | Accessibility pass | Keyboard order, focus ring, contrast and reduced motion are checked against DESIGN.md section 8. | `cd web && npm run a11y` (axe + Tab walk, both themes, 1440 and 390 px, with `python -m server --fake` running). Still open: a manual pass with VoiceOver or NVDA on a live run. |
| 4.7 | Canvas additions | Approval card, interrupted outcome and stop confirm are added to the design canvas. | visual review |

## M5: Phone extras
| # | Task | Done when | Tests |
|---|---|---|---|
| 5.1 | ntfy | Push on finished, out of budget, crashed and approval needed, with a link to the run. Off when `NTFY_URL` is unset. | fake HTTP: right events send, others don't |
| 5.2 | iPhone widget | `widgets/scriptable.js` shows the running task, usage and last result from `/api/status`, with Access service-token headers. | manual on a phone |
| 5.3 | Android widget | `widgets/android-kwgt.md` step-by-step guide. Tasker makes the request (KWGT can't send auth headers) and hands values to KWGT. | manual |
| 5.4 | PWA install | Manifest and icons so "Add to Home Screen" opens full screen. | Chromium `Page.getInstallabilityErrors` is empty (Lighthouse 12 dropped its PWA audit); `tests/test_pwa.py` |

## M6: Portfolio replay
| # | Task | Done when | Tests |
|---|---|---|---|
| 6.1 | Replay page | `replay/` is a static build that plays a recorded `log.jsonl` with the same reducer and components, with play, pause and speed controls. No server. | Vitest on the player clock, build with no API calls |
| 6.2 | Publish | Deployed to GitHub Pages from a recorded real run, with secrets and paths scrubbed. | manual |

## M7: Parallel and cheaper (after v1, PRD section 13)
| # | Task | Done when | Tests |
|---|---|---|---|
| 7.1 | Dependencies and parallel tasks | `assign_task` takes `depends_on` and `owns` (files). Ready tasks run together up to `max_parallel` (default 3). Stop cancels all. | fake runner: 3 independent tasks overlap in time; a dependent one waits; two tasks can't own the same file |
| 7.2 | Model tier per task | `create_agent`/`assign_task` take `tier` (haiku, sonnet, opus) with a reason. A failed task retries one tier up, once. New event fields shown on the task card. | tier passed to the runner; step-up on failure; event and fixture updated |
| 7.3 | Cheap checks first | A `done_when` with a `check:` command runs it before the model checker; a failing command skips the model call. | command pass/fail paths; model checker not called when the command fails |
| 7.4 | Usage per agent and model | `usage` events carry agent, task and model. Run page shows a breakdown. | totals add up; UI renders the breakdown |
| 7.5 | Cheap preset and hidden limits in Options | One-click Cheap preset; tries per task, steps per try and max assignments in Options. | options posted correctly |

## M8: Teams and schedules (after v1)
| # | Task | Done when | Tests |
|---|---|---|---|
| 8.1 | Team model | `teams/<id>/team.json` (members, tiers, tools, schedule, budget) and `memory.md`. CRUD API. | create, edit, delete; memory read into each run's first prompt |
| 8.2 | Team room | Your messages and agent-to-agent hand-off messages in one chat view, from the event log. | room shows both kinds; you can post mid-run (needs steering) |
| 8.3 | Triggers | Schedule (cron-like, in your time zone), room message, and data webhook each start a linked run. Sleeps in between. | fake clock fires on time; no run without a trigger |
| 8.4 | Team budget | Usage per day per team; a trigger over budget is skipped with a push. (If you decide on a cap.) | skip path and push |

## M9: Team builder (after v1)
| # | Task | Done when | Tests |
|---|---|---|---|
| 9.1 | Propose a team | One message ("a team for stocks") gives a proposal: members, tools, tiers, schedule, outputs, approvals, missing tools as setup steps. Questions for gaps. Save on your OK. | fake orchestrator: proposal shape; missing tools listed, never invented |
| 9.2 | Example: TikTok team | Research, scripts, Remotion videos, posting with approval, stats review. | demo scenario; posting always asks |
| 9.3 | Example: stocks team | Watchlist, daily brief, research on request, alerts. No trading tools. "Not financial advice" in briefs. | demo scenario; no trading tool in the catalog |

## Later
Steering mid-run, Docker per agent, OpenRouter models, repo diff, hosting setup (always-on machine,
Cloudflare Tunnel + Access). See `docs/ARCHITECTURE.md` section 17.

## First manual end-to-end test (end of M1, against a real model)
Run this on your laptop before any UI work.

1. Check the login and billing mode.
   ```bash
   echo $ANTHROPIC_API_KEY      # must print nothing
   claude                       # if asked, run /login and pick your Pro account, then exit
   ```
2. Install and run the offline tests.
   ```bash
   pip install -r requirements.txt
   python -m pytest tests -q
   ```
3. Start a small research run with a low cap.
   ```bash
   python main.py --max-cost 2 --max-agents 3 "Research the top 3 Indonesian e-wallets and write report.md with a fee table and at least 5 source URLs"
   ```
4. While it runs, check that the terminal shows, in order:
   - `run_started`
   - `orchestrator_said`
   - `agent_created`, more than once
   - `task_assigned`, each with a title
   - `attempt_started`
   - `worker_activity` lines
   - `checker_started`
   - `task_passed` or `attempt_failed`
   - `finished`
5. When it ends, open `runs/<newest>/`:
   - `log.jsonl` has `seq` 1, 2, 3… with no gaps
   - `workspace/report.md` exists, has a fee table and 5+ URLs
   - `final.md` describes the result
   - `meta.json` shows `"auth_mode": "plan"`
6. Test stop: start the same command again and press Ctrl+C after the first `task_assigned`. The log
   should end with `run_stopped`, and `board.json` should be saved.
7. Test the browser tool. This needs Node for `npx`.
   ```bash
   python main.py --max-cost 1 "Open https://example.com in the browser and save the page title to title.txt"
   ```
   `agent_created` should list `browser` in its tools, and `title.txt` should say "Example Domain".
8. Write down anything surprising as a Learning in AGENTS.md, and fix bugs with a test each.

Pass when steps 4 to 7 all hold.
