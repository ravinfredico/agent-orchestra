# Handover: ChaCha PA

Last updated: 2026-11-24. Read this first in a new session, then `AGENTS.md`.

## Where things are
| What | Where |
|---|---|
| Working branch | `feat/chacha-pa` (pushed). All code lives here. |
| Docs-only branch | `claude/adoring-wright-xydai5`: docs up to the implementation plan. `feat/chacha-pa` branches from it. |
| `main` | Original CLI only. Nothing merged yet. No PR opened (the user hasn't asked for one). |
| Design canvas | https://claude.ai/artifact/1VhNwtUMKpMpNrVvbyhNUS (private to the user). Page "Screens" has 13 screens. Page "Style & components" has the Thread sheet and the Character component. |
| Decisions | `docs/PLAN.md` |
| Plan and progress | `docs/IMPLEMENTATION.md` (Progress table at the top) |

## What's built (all tested offline, never run against a real model)
- **Engine (`orchestra/`):**
  - Event log with `seq`, plus listeners.
  - Task titles and short checker reasons.
  - Tool catalog (`tools.catalog.json` + `plugins/`): builtins, Playwright browser, Gmail, Calendar.
  - Approvals for outward tools.
  - SDK sandbox for shell.
  - Stop, crash kinds, continue and follow-up.
  - Playbooks (`orchestra/playbooks/*.md`, read with `read_playbook`).
- **Server (`server/`):**
  - FastAPI with several runs at once, and SSE that replays from `Last-Event-ID`.
  - SQLite index with search.
  - Files, zip and delete.
  - `APP_TOKEN` auth and a host guard.
  - `/api/status` for widgets.
  - Recovery marks unfinished runs `interrupted`.
- **Web (`web/`):** React 19 + Vite + TypeScript, matching the canvas:
  - new run with Options (playbook, connectors and plugins)
  - live thread with characters, task cards, approvals and outcomes
  - history, file viewer
  - dark and light themes, phone layout
- **Tests:** 62 pytest (`python -m pytest tests -q`), 16 Vitest (`cd web && npm test`), type-checked
  (`npx tsc -b`), and an axe + keyboard audit (`cd web && npm run a11y`).

## How to run
```bash
pip install -r requirements.txt
```
```bash
cd web && npm install && npm run build && cd ..
```
```bash
python -m server --fake
```
`--fake` plays a scripted run with no model calls. It picks the scenario from the task text:
build-style tasks ("build", "app", "tests"…) play a developer + tester building a todo CLI whose
tests really pass (`orchestra/demo_files/`); anything else plays the e-wallet research report.
Drop `--fake` to use the real Claude plan login.
Open http://127.0.0.1:8000.

## Next steps, in order
1. **First live run on the user's laptop** (`docs/IMPLEMENTATION.md`, "First manual end-to-end
   test"). This can't be done in a cloud session: it needs their Claude login, and `ANTHROPIC_API_KEY`
   must stay unset. Expect engine bugs. Fix each one with a test.
2. **Connectors check (task 1.13):** can an SDK session started with the user's Claude login reach
   their claude.ai Gmail and Calendar connectors? Until then, both are MCP entries that need
   `GMAIL_MCP_URL/TOKEN` and `GCAL_MCP_URL/TOKEN` in `.env` (see `.env.example`).
3. **M4 leftovers:**
   - a manual screen reader pass (VoiceOver or NVDA) on a live run. The automated part is done:
     `cd web && npm run a11y` is clean in both themes at 1440 and 390 px
   - add the approval card, interrupted outcome, stop confirm, playbook line, Playbook select and
     connector picker to the canvas (ask before editing it)
4. **M5:** ntfy push, widgets (`widgets/scriptable.js` for iPhone, `widgets/android-kwgt.md`), PWA install.
5. **M6:** static replay page for the portfolio.
6. **Later:**
   - steering (message the orchestrator mid-run)
   - Docker sandbox per agent
   - OpenRouter models (needs its own API key)
   - repo diff view
   - hosting (decide own machine vs VPS first)

## Decided (don't re-ask)
- Product name is **ChaCha PA**. Design direction is Thread with agents as characters, minimal like
  Grok-style chat apps.
- Runs use the **Claude Pro plan login**, not API billing. On a VPS, use an API key (Anthropic's terms).
- Hosting: Cloudflare Tunnel + Access. *Where* to host is still open, but not needed until the hosting
  milestone.
- Several runs at once. Stop cancels immediately. A server restart marks runs interrupted.
- Notifications: ntfy push + home-screen widget on both iPhone and Android.
- Live detail: events + one activity line per worker. A usage meter that jumps is fine.
- Repos when hosted: allowlisted folder (`REPOS_ROOT`) now, Docker later.
- History actions: delete, zip, rerun with edits.
- Extras kept: task titles, "Continue with $X more", follow-up box, plan-mode indicator.
- Claude only in v1; OpenRouter later.
- Outward actions always ask first.
- Agents can be any role.
- Borrowed from Lauren Tan: orchestrator playbooks, and pstack for development.

## Gotchas
- **pstack** (`.claude/settings.json`) loads from the next session on. Its hook routes multi-file work
  to `pstack:poteto-mode`. AGENTS.md wins on conflicts.
- **Figma:** the connected Figma account is **not the user's**. Don't publish to Figma until they confirm
  their account.
- **Design first:** work goes in the Claude Design canvas, then code. No hand-made HTML prototypes.
- **Questions:** ask with AskUserQuestion, giving concrete options.
- **Commits:** gate them on the test exit code. Piping pytest through `tail` hid a failure once.
- **New event type:** update ARCHITECTURE section 7, the DESIGN event map, `server/summary.py`,
  `web/src/state/reducer.ts`, then run `python scripts/make_fixtures.py`.
- **CSS:** prefix state classes (`pip-done`). A generic `.empty` class once broke the task cards.
- **UI changes:** check them in a browser with Playwright at 1440 and 390 px before calling them done.
- **`web/dist`** is not committed. Build it before `python -m server` serves the app.
