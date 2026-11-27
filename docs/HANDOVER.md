# Handover: ChaCha PA

Last updated: 2026-11-27. Read this first in a new session, then `AGENTS.md`.

## Where things are
| What | Where |
|---|---|
| `main` | Has everything (PRs #2 and #3 merged). Same code as `feat/chacha-pa`. Work on a branch and let the user merge. |
| Working branch | `feat/chacha-pa`. |
| Docs-only branch | `claude/adoring-wright-xydai5`: old, docs up to the implementation plan. |
| Demo video | `docs/media/chacha-pa-demo.mp4` (97 s, voiceover), README GIF `docs/media/chacha-pa-demo-preview.gif`, source `demo-video/`. |
| Design canvas | https://claude.ai/artifact/1VhNwtUMKpMpNrVvbyhNUS (private to the user). Page "Screens" has 13 screens plus the `M7-Cheaper` sheet (tier chip, cheap checks, Cheap preset, parallel cards, usage by agent and model). Page "Style & components" has the Thread sheet and the Character component. |
| Decisions | `docs/PLAN.md` |
| Plan and progress | `docs/IMPLEMENTATION.md` (Progress table at the top) |

## What's built (tested offline; the first live run on Windows worked, M7 and M8 not yet tried live)
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
- **M7 (after v1), done offline:**
  - model tier per agent and task (haiku, sonnet, opus) with a reason; a failed try steps up one tier, once, up to `max_tier`
  - cheap checks (`orchestra/checks.py`) before the model checker; `checks_only` skips it
  - Options: Default and Cheap presets, highest model, tries, steps, max tasks, tasks at once
  - `assign_tasks`: parallel batches with `depends_on` and `owns`, one task per agent at a time
  - usage by agent and by model in the rail
- **M8 (after v1), done offline:** saved teams (`server/teams.py`, `teams/<id>/`), members created up
  front, memory in the first prompt plus a line per finished run, triggers (room message, schedule,
  secret webhook), steering (message a running orchestrator, also from the run page), team room,
  team editor, Teams in the sidebar.
- **M6 replay page:** `web/src/replay/`, built with `npm run build:replay`, published by
  `.github/workflows/replay-pages.yml` once Pages is turned on (Settings → Pages → Source: GitHub Actions).
- **Tests:** 116 pytest (`python -m pytest tests -q`), 37 Vitest (`cd web && npm test`), type-checked
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
1. **Turn on GitHub Pages** (user, once): Settings → Pages → Source: "GitHub Actions". The replay
   page then deploys on pushes to `main` that touch `web/` (or run "Replay page" in the Actions tab).
2. **Try M7 and M8 live:** a Cheap run (does the orchestrator use tiers, checks, `assign_tasks`?),
   then a small team with one schedule slot and a mid-run message. Fix misses in the playbooks.
3. **Connectors check (task 1.13):** can an SDK session started with the user's Claude login reach
   their claude.ai Gmail and Calendar connectors? Until then, both are MCP entries that need
   `GMAIL_MCP_URL/TOKEN` and `GCAL_MCP_URL/TOKEN` in `.env` (see `.env.example`).
4. **M9 team builder:** "I want a team for stocks" gives a proposed team (members, tools, tiers,
   schedule, outputs, approvals, missing tools as setup steps) to review and save into the M8 team
   editor. TikTok and stocks are the first examples.
5. **Leftovers:**
   - a manual screen reader pass (VoiceOver or NVDA) on a live run
   - draw the approval card, interrupted outcome, stop confirm, playbook line, Playbook select and
     connector picker on the canvas (ask before editing it)
   - try the phone widgets on real phones (needs hosting)
   - re-render the demo video (`demo-video/`) after big UI changes
6. **Later:** Docker sandbox per agent, OpenRouter models (needs its own API key), repo diff view,
   hosting (decide own machine vs VPS first; always-on teams need a machine that stays on).

## Decided (don't re-ask)
- After v1: parallel agents; the orchestrator picks the cheapest model tier per task; teams for any
  goal from one message; teams are always on but only spend usage on triggers; TikTok team does
  ideas, scripts, rendered videos, posting (with approval) and stats review; stocks team never trades.
- Teams: no daily cap; room messages steer a running team; schedules use the team's time zone.
- Open: plan login vs API key for teams,
  which machine hosts always-on teams, TikTok API access, stocks markets and data source.
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
- **The user is on Windows** (PowerShell). `py` is not installed there; use `python`. The app has
  run on Windows once (first live run, fine). Watch for path and sandbox issues in new features.
- **Usage burns fast** for the user. Keep sessions short, prefer Sonnet for routine work, and suggest
  haiku workers and low caps for test runs.
- **pstack** (`.claude/settings.json`) loads from the next session on. Its hook routes multi-file work
  to `pstack:poteto-mode`. AGENTS.md wins on conflicts.
- **Figma:** the connected Figma account is **not the user's**. Don't publish to Figma until they confirm
  their account.
- **Design first:** work goes in the Claude Design canvas, then code. No hand-made HTML prototypes.
- **Questions:** ask with AskUserQuestion, giving concrete options.
- **Decided in M7:** check commands run only when shell is on; opus step-up is allowed by default (Cheap caps at sonnet); canvas first for UI.
- **Commits:** gate them on the test exit code. Piping pytest through `tail` hid a failure once.
- **New event type:** update ARCHITECTURE section 7, the DESIGN event map, `server/summary.py`,
  `web/src/state/reducer.ts`, then run `python scripts/make_fixtures.py`.
- **CSS:** prefix state classes (`pip-done`). A generic `.empty` class once broke the task cards.
- **UI changes:** check them in a browser with Playwright at 1440 and 390 px before calling them done.
- **`web/dist`** is not committed. Build it before `python -m server` serves the app.

## Handover prompt (paste into a new session)
```
You're continuing ChaCha PA in ravinfredico/agent-orchestra. Work on branch feat/chacha-pa
(main has the same code). First read docs/HANDOVER.md, then AGENTS.md, then PRD section 13.

State: v1 milestones M1 to M5, M7 and M8 are done and tested offline (116 pytest, 37 Vitest), plus the M6 replay page. The first live run worked. I'm on Windows (use `python`, not `py`), and my Claude usage burns fast, so
keep this session lean and prefer cheap models.

Task: the claude.ai connectors check (task 1.13), then M9 (team builder: "I want a team for stocks"
gives a proposed team to review and save).
Follow AGENTS.md: tests for new logic, run pytest before every commit, update the docs, and list
doc changes at the end. Ask me (with options) before anything only I can decide. Push to
feat/chacha-pa; don't merge to main or open a PR unless I ask.
```
