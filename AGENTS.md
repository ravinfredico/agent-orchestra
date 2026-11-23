# AGENTS.md

Shared instructions for any AI coding agent working in this repo. Keep this file under about 200 lines.

## Overview
Agent Orchestra is a multi-agent harness on the Claude Agent SDK (Python). An orchestrator agent
plans a task and creates its own worker agents at runtime: it writes their system prompts and picks
their tools from a catalog. It assigns each task with a concrete `done_when`, and loops until an
independent checker passes every task.

**ChaCha PA** is the web app being built around it: type a task, watch the team work live, on laptop
or phone. Runs on the user's Claude Pro plan through the Claude Code login (`ANTHROPIC_API_KEY`
unset). API-key mode is also supported.

Docs:
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
| `orchestra/tools.py` | `OrchestraTools`: create_agent, assign_task (inner loop), view_board, finish, as in-process MCP server `orchestra` |
| `orchestra/approvals.py` | `ApprovalBroker` + `can_use_tool` callback for outward tools |
| `orchestra/playbooks/` | one markdown playbook per task type; `playbooks.py` loads them, `read_playbook` serves them |
| `orchestra/orchestrator.py` | `create_run()` / `execute_run()` outer loop, continue and follow-up prompts |
| `orchestra/state.py` | `RunState`: agents, board, usage, `log()` event envelope to `runs/<id>/log.jsonl` |
| `orchestra/fake.py` | scripted runner + client for offline tests and demo mode (never used by default) |
| `orchestra/gitsafe.py` | `--repo` safety: clean tree, branch `orchestra/<ts>`, `REPOS_ROOT` allowlist |
| `server/` | FastAPI app (`app.py`), `RunManager` (`runs.py`), log folding (`summary.py`), SQLite index, auth |
| `web/` | React + Vite + TypeScript app. `src/state/reducer.ts` mirrors `server/summary.py` |
| `tools.catalog.json` | tools the orchestrator may give agents |
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
python scripts/make_fixtures.py                # after changing events: refresh web fixtures
```

## Conventions
- Handlers in `OrchestraTools` are plain async functions, so tests can use a fake runner.
- Workers can never create agents. The orchestrator has no built-in tools (`tools=[]`).
- Agents only get tools from the catalog. Never let the orchestrator invent tools.
- All agents use `setting_sources=[]`. Use `permission_mode="dontAsk"`, except agents with outward
  tools, which use the approval callback.
- Use model aliases (`sonnet`, `haiku`, `opus`), not dated model IDs.
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
- Never commit `runs/`, `.env`, tokens or API keys. Catalog secrets are `${VAR}` references only.
- Outward actions (send, post, book) always need user approval.
- Shell stays off by default and runs sandboxed when on.
- Don't set `ANTHROPIC_API_KEY` in code or tests. Plan mode depends on it being unset.
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
- Branch `feat/chacha-pa`. M1 (engine), M2 (server), M3 and M4 (web app) done and tested offline.
- Orchestrator playbooks added (pstack-style). pstack is enabled for development (see CLAUDE.md).
- Not yet run against a real model. Next: the first live run (IMPLEMENTATION.md, end of M1), then the
  claude.ai connectors check (task 1.13), then M5 (ntfy, widgets, PWA) and M6 (replay page).

## Learnings
- Design work goes into a design tool (Claude Design canvas, then Figma) before any HTML. No
  hand-built HTML prototypes.
- Ask the user open questions directly, with concrete options for each, rather than listing them
  in a doc.
- Check with the user before touching Figma: the connected Figma account is not theirs.
- Check UI work in a real browser (Playwright screenshots at 1440 and 390 px) before calling it done.
- Gate commits on the test exit code (`python -m pytest tests -q && git commit ...`). Piping pytest into `tail` hides failures.
- Fix recurring run failures in the matching playbook (`orchestra/playbooks/`), not only in prompts.
- Random ids need enough bits for bursts: run-id suffixes are 6 hex, and `create_run` never reuses a folder.
