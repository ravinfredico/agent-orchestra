# AGENTS.md

Shared instructions for any AI coding agent working in this repo. Keep this file under about 200 lines.

## Overview
Agent Orchestra is a multi-agent harness on the Claude Agent SDK (Python). An orchestrator agent
plans a task and creates its own worker agents at runtime: it writes their system prompts and picks
their tools from a catalog. It assigns each task with a concrete `done_when`, and loops until an
independent checker passes every task.

**ChaCha PA** is the web app being built around it: type a task, watch the team work live, on laptop
or phone. It never touches logins: it runs the installed Claude Code with whatever sign-in it has
(the user's Claude plan for personal use, or `ANTHROPIC_API_KEY`). Self-hosted only; see README
"Sign-in and terms".

Docs:
- `docs/HANDOVER.md` start here in a new session: state, next steps, gotchas
- `docs/PLAN.md` decisions
- `docs/PRD.md` requirements
- `docs/DESIGN.md` screens, states, tokens
- `docs/ARCHITECTURE.md` API, events, refactors
- `docs/IMPLEMENTATION.md` milestones and tasks

## Layout
| Path | What |
|---|---|
| `main.py` | CLI entry |
| `orchestra/config.py` | models, `Budget` limits, `Config.to_options()/from_options()` |
| `orchestra/catalog.py` | tool catalog: loads `tools.catalog.json` + `plugins/`, maps ids to SDK options |
| `orchestra/prompts.py` | orchestrator and checker prompts, checker JSON schema |
| `orchestra/runner.py` | `run_agent()`: one agent via `claude_agent_sdk.query()`, forwards tool use |
| `orchestra/tools.py` | `OrchestraTools`: create_agent, assign_task (inner loop), assign_tasks (parallel batch), view_board, finish, as in-process MCP server `orchestra` |
| `orchestra/connectors.py` | your claude.ai connectors: discovery (`claude mcp list`), catalog entries, read patterns |
| `orchestra/checks.py` | cheap checks run before the model checker (files, words, commands when shell is on) |
| `mcp_servers/` | MCP servers that ship with the app: `tiktok.py` (stats, drafts, posts). Catalog entries start them with `${PYTHON}` and `${ORCHESTRA_ROOT}` |
| `orchestra/approvals.py` | `ApprovalBroker` + `can_use_tool` callback for outward tools |
| `orchestra/playbooks/` | one markdown playbook per task type; `playbooks.py` loads them, `read_playbook` serves them |
| `orchestra/builder.py` | team builder (M9): one model call turns a message into a proposed team; missing tools become setup steps |
| `orchestra/orchestrator.py` | `create_run()` / `execute_run()` outer loop, continue and follow-up prompts |
| `orchestra/state.py` | `RunState`: agents, board, usage, `log()` event envelope to `runs/<id>/log.jsonl` |
| `orchestra/fake.py` | scripted runner + client for offline tests and demo mode (never used by default); `pick_demo()` chooses the research or build scenario |
| `orchestra/gitsafe.py` | `--repo` safety: clean tree, branch `orchestra/<ts>`, `REPOS_ROOT` allowlist |
| `server/` | FastAPI app (`app.py`), `RunManager` (`runs.py`), log folding (`summary.py`), SQLite index, auth, ntfy pushes (`notify.py`), teams + triggers + room (`teams.py`) |
| `orchestra/envfile.py` | loads `.env` at startup (shell wins, never `ANTHROPIC_API_KEY`) |
| `web/` | React + Vite + TypeScript app. `src/state/reducer.ts` mirrors `server/summary.py`; `src/presets.ts` holds the Options presets |
| `tools.catalog.json` | tools the orchestrator may give agents |
| `demo-video/` | Remotion project for the demo video (`docs/media/chacha-pa-demo.mp4`); footage is demo-mode recordings |
| `replay/` | static replay page for the portfolio (README); source in `web/src/replay/`, Pages workflow in `.github/workflows/` |
| `widgets/` | phone home-screen widgets: `scriptable.js` (iPhone), `android-kwgt.md` (Android guide) |
| `scripts/make_fixtures.py` | regenerates the web test fixtures from the Python demo scenario |

## The three loops
1. **Agent loop:** the SDK runs each agent until it stops.
2. **Inner loop** (`assign_task`): worker attempt, then checker (read-only tools, plus Bash if
   allowed), then feedback and retry, up to `max_attempts_per_task`.
3. **Outer loop** (`orchestrator.py`): the orchestrator replans on FAILED. `finish` refuses while
   tasks are unfinished. A new task can supersede a failed one with `replaces`. The engine nudges the
   orchestrator if it stops before `finish` is accepted.

## Commands
```bash
pip install -r requirements.txt
python -m pytest tests -q                      # engine + server, offline, no model calls
python main.py "task"                          # CLI run
python main.py --allow-bash --repo PATH "task" # coding task on an existing repo
cd web && npm install && npm run build         # build the app into web/dist
python -m server                               # app + API on http://127.0.0.1:8000
python -m server --fake                        # demo mode: scripted runs, no model calls
cd web && npm test && npx tsc -b               # web tests + typecheck
cd web && npm run dev                          # dev server on :5173, proxies /api to :8000
cd web && npm run a11y                         # axe + keyboard audit; needs python -m server --fake running
cd web && npm run build:replay                 # static replay page into replay/dist (npm run a11y:replay checks it)
python scripts/make_fixtures.py                # after changing events: refresh web fixtures
```

## Conventions
- Handlers in `OrchestraTools` are plain async functions, so tests can use a fake runner.
- Workers can never create agents. The orchestrator has no built-in tools (`tools=[]`).
- Agents only get tools from the catalog. Never let the orchestrator invent tools.
- All agents use `setting_sources=[]`. Use `permission_mode="dontAsk"`, except agents with outward
  tools, which use the approval callback.
- Use model aliases (`sonnet`, `haiku`, `opus`), not dated model IDs. Tiers are ordered in `config.TIERS`.
- Events: one envelope `{seq, run_id, t, type, ...}`, defined in `docs/ARCHITECTURE.md` section 7.
  A new event type needs an entry there, a row in the event-to-UI map in `docs/DESIGN.md`, handling in
  `server/summary.py` and `web/src/state/reducer.ts`, and fresh fixtures (`scripts/make_fixtures.py`).
- A terminal event (`finished`, `run_failed`, `run_stopped`, `run_interrupted`) is always the last line
  of a log. `finish` only sets `pending_finish`; the outer loop logs `finished` after the last usage.
- Web CSS: prefix state classes with their component (`pip-done`, `dot-pass`). Never reuse generic
  names like `.empty` for states.
- `runs/<id>/log.jsonl` is the source of truth. Everything else can be rebuilt from it.
- Docs are plain English: short sentences, no jargon or filler, lists and tables where they help.

## Rules
- Keep `python -m pytest tests -q` passing. Run it before every commit.
- Add tests for new logic. Engine and server tests stay offline: fake the runner, never call a model.
- Never expose the server publicly without auth. Bind to 127.0.0.1. Hosting goes through Cloudflare
  Tunnel + Access + `APP_TOKEN`.
- Never commit `runs/`, `teams/`, `.env`, tokens or API keys. Catalog secrets are `${VAR}` references only.
- Outward actions (send, post, book) always need user approval.
- Shell stays off by default and runs sandboxed when on.
- Don't set `ANTHROPIC_API_KEY` in code or tests. Plan mode depends on it being unset.
- Never add login code: no sign-in screens, no reading or storing Claude credentials or tokens.
- Keep the CLI working when changing the engine.

## Self-improvement
These files are meant to get better over time.
- **When the user corrects you, or you hit a mistake or gotcha,** add a short rule to Learnings
  below. Write the rule, not the story ("Run X before Y", not "Yesterday X broke because…").
- **After finishing a milestone,** update Status and any section that is now out of date (Layout,
  Commands, Conventions).
- **Keep it lean:** merge duplicates, delete learnings that no longer apply, and keep this file
  under about 200 lines. Move long detail into `docs/`.
- **At the end of each task,** list any changes you made to AGENTS.md, CLAUDE.md or `docs/` in your
  summary, so the user can see what was learned.

## Status
- Branch `feat/chacha-pa`. M1 to M8 done and tested offline. M9 team builder (9.1, 9.4 marketing demo) done offline.
- Orchestrator playbooks added (pstack-style). pstack is enabled for development (see CLAUDE.md).
- M7 (parallel and cheaper) done offline: model tier per task with one step-up, cheap checks,
  Cheap preset, `assign_tasks` with dependencies, usage by agent and model.
- M8 (teams, triggers, steering, room) done offline. No daily cap (user's decision).
- M6 replay page built; publishing waits for you to turn on GitHub Pages (Actions source).
- claude.ai connectors in the catalog, scoped per agent (built offline; confirm live, task 1.13).
- First live run worked (2026-11-27). Not yet tried live: M7, teams, connectors, a real team proposal.
- `main` has v1 (PRs #2, #3); M7 onward is only on `feat/chacha-pa` (the working branch).

## Learnings
- Write multi-line edits as a Python script file, not a bash heredoc: Claude Code's removal check can block heredocs it can't parse.
- Design work goes into a design tool (Claude Design canvas, then Figma) before any HTML. No
  hand-built HTML prototypes.
- Ask the user open questions directly, with concrete options for each, rather than listing them
  in a doc.
- Check with the user before touching Figma: the connected Figma account is not theirs.
- Check UI work in a real browser (Playwright screenshots at 1440 and 390 px) before calling it done.
- Gate commits on the test exit code (`python -m pytest tests -q && git commit ...`). Piping pytest into `tail` hides failures.
- Fix recurring run failures in the matching playbook (`orchestra/playbooks/`), not only in prompts.
- Random ids need enough bits for bursts: run-id suffixes are 6 hex, and `create_run` never reuses a folder.
- A new session may start from `main`, which has none of this work. Fetch all branches and read
  `docs/HANDOVER.md` on the working branch before doing anything.
- Off-canvas drawers need `visibility: hidden` when closed, or Tab walks through invisible links.
- Team members get only tools usable now (`catalog.available_ids`); `create_agent` rejects the rest, so a
  signed-out connector once dropped a whole member.
- Amber (`--check`) text fails contrast on light grey; use it for borders, `--text-2` for the words.
- Run `npm run a11y` after UI changes. Wait for enter animations before axe, or it measures half-faded colors.
