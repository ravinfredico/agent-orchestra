# Handover: ChaCha PA

Last updated: 2026-11-28. Read this first in a new session, then `AGENTS.md`.

## Where things are
| What | Where |
|---|---|
| `main` | Has v1 (PRs #2 and #3). Everything from M7 on is only on `feat/chacha-pa`; the user merges when ready. |
| Working branch | `feat/chacha-pa`. |
| Docs-only branch | `claude/adoring-wright-xydai5`: old, docs up to the implementation plan. |
| Demo video | `docs/media/chacha-pa-demo.mp4` (97 s, voiceover), README GIF `docs/media/chacha-pa-demo-preview.gif`, source `demo-video/`. |
| Design canvas | https://claude.ai/artifact/1VhNwtUMKpMpNrVvbyhNUS (private to the user). Page "Screens" has 13 screens plus the `M7-Cheaper`, `M8-Teams`, `M6-Replay` and `M9-Builder` sheets (tier chip, cheap checks, Cheap preset, parallel cards, usage by agent and model). Page "Style & components" has the Thread sheet and the Character component. |
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
- **Claude connectors (the main direction):** teams use the user's claude.ai connectors (Figma, Gmail,
  Notion, Slack…). `orchestra/connectors.py` finds them with `claude mcp list`; each agent sees only
  its own; reads are free, everything else asks. Built on Claude Code's docs, not yet checked live.
- **Video-team tools (PRD section 13, "Making the TikTok team real"):** `elevenlabs` and `tiktok`
  catalog entries, `mcp_servers/tiktok.py`, `short-video` playbook. Need `ELEVENLABS_API_KEY` (+ uv)
  and `TIKTOK_ACCESS_TOKEN` in `.env`; not tried live yet.
- **M9 team builder (done offline):** `/teams/new` takes one message ("I want a marketing team") and
  shows a proposal: members, tiers, tools (lock = asks first), schedule, outputs, approvals, setup steps
  ("Connect Gmail at claude.ai", "Sign in to Slack: /mcp") and up to 2 questions. Save, or Edit before
  saving (the M8 editor, prefilled). `orchestra/builder.py`, `POST /api/teams/propose`. Real mode: one
  sonnet call, no tools. Demo mode: marketing team (TikTok for video words, stocks for watchlist words), and a marketing team run
  (Notion research, posts, Figma visuals with approval, plan and newsletter; Slack skipped as signed out).
- **Stocks team (9.3, done offline):** scout (news), analyst (prices, earnings dates; a market-data API is
  a setup step), writer (brief). Alerts through the webhook. The builder always refuses trading and
  payment tools and adds a never-trade rule to finance teams; the demo checker rejects a brief that says
  "buy" and the brief ends "Not financial advice."
- **M10 video studio (done offline):** `/teams/<id>/studio` lists the videos a team saved
  (`videos/<name>.mp4` + `videos/<name>.md` with title, `Caption:` line, hashtags): play, Copy caption
  (caption plus hashtags), Download, Open script, Mark posted / Undo. "Script only" when no mp4. Room
  and Studio tabs show for video teams. `server/studio.py`. The TikTok team and the `short-video`
  playbook save to the studio and never post.
- **M6 replay page:** `web/src/replay/`, built with `npm run build:replay`, published by
  `.github/workflows/replay-pages.yml` once Pages is turned on (Settings → Pages → Source: GitHub Actions).
- **Tests:** 148 pytest (`python -m pytest tests -q`), 46 Vitest (`cd web && npm test`), type-checked
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
marketing teams play the 4-member marketing team; stocks or watchlist teams play the 3-member stocks desk; TikTok or video tasks and teams play a 5-member TikTok team (trends and stats in parallel, scripts, renders,
posting with approval);
build-style tasks ("build", "app", "tests"…) play a developer + tester building a todo CLI whose
tests really pass (`orchestra/demo_files/`); anything else plays the e-wallet research report.
Drop `--fake` to use the real Claude plan login.
Open http://127.0.0.1:8000.

## Live checks (2026-11-28, from a cloud session, Cheap caps, about $0.15 in total)
The `claude` CLI in the cloud container is signed in, so live runs work there (`python -m server
--port 8001`, real mode). What happened:
| Check | Result |
|---|---|
| Cheap run (two files, then an index) | Passed, $0.04. Haiku tier with a reason, `assign_tasks` with `depends_on`, cheap checks. Fixed: `checks_only` with only `file_exists` is now ignored (content wasn't judged); the prompt now says parallel tasks need different agents (it used one agent, so nothing ran at once). |
| Real team proposal ("business advisory team for my coffee shop") | Passed, 11 s, $0.02. 3 members, a Monday slot, 2 questions, a correct "turn on Shell" setup step. |
| Team run + mid-run message | Passed, $0.09. The message steered the run (`steered: true`), the saved notes were used, memory got a line. |
| Connectors | Not checkable here: this container has no claude.ai connectors (`claude mcp list` shows only `plugin:` servers). Still needs the user's laptop or VPS. |
Small leftover seen: the room shows the final answer twice (the orchestrator's last message and the
`finished` result).

## What's missing (as of 2026-11-28)
### A. Can be built in a cloud session
1. **Hosting on a VPS (next milestone):** setup guide and scripts for a VPS: service file, Cloudflare
   Tunnel + Access, `APP_TOKEN`, Claude Code installed and signed in. See the terms note under Decided.
2. **Room shows the final answer twice:** drop the orchestrator's last message when it repeats the
   `finished` result (`server/teams.py` `room_items`, and the run thread if it does the same).
3. **Video rendering for real:** the TikTok team needs Shell on and Remotion in the sandbox to make
   mp4s; without it the studio shows "script only". Try one render live with low caps.
4. **Re-render the demo video** (`demo-video/`) with teams, the builder and the studio (ask first).

### B. Needs the user's machine or the VPS
5. **Connectors live check (task 1.13):** `claude mcp list` shows `claude.ai ...` connectors; Options
   lists them; a worker uses one; a write asks.
6. **ElevenLabs voiceovers:** `ELEVENLABS_API_KEY` and uv.
7. **Screen reader pass** (NVDA on Windows) on a live run.
8. **Phone widgets on real phones** (after hosting).

### C. User, one time
9. **Turn on GitHub Pages** (Settings → Pages → Source: "GitHub Actions") for the replay page.

### Dropped (user, 2026-11-28)
- Demo-mode builder gap: the user doesn't need demo mode. It stays only for tests and offline checks.
- TikTok token refresh (9.2b) and TikTok posting: no token; the user posts by hand from the studio.

### Later (not committed)
Docker sandbox per agent, OpenRouter models (own API key), repo diff view.

## Decided (don't re-ask)
- Sign-in: the app never touches logins; it runs the user's installed Claude Code. Self-hosted, open
  source. Plan login for personal use; API key for anyone who shares, hosts or automates heavily
  (README "Sign-in and terms"). Never add login code.
- After v1: parallel agents; the orchestrator picks the cheapest model tier per task; teams for any
  goal from one message; teams are always on but only spend usage on triggers; TikTok team does
  ideas, scripts and rendered videos saved to the studio (you post by hand); stocks team never trades.
- Teams are built around the user's claude.ai connectors (TikTok is just one example).
- Teams: no daily cap; room messages steer a running team; schedules use the team's time zone.
- Decided 2026-11-28: host on a **VPS**; teams keep the **plan login**; TikTok is posted **by hand**
  from the studio (no TikTok API, no token); stocks teams take the market from the prompt (US or
  Indonesia), with web search as the data source.
- **Terms note (flag it again before hosting):** Anthropic's docs point to an API key for a server
  (PRD section 11 risk). The user chose plan login on the VPS; recheck Anthropic's current terms
  before the hosting milestone and switch to `ANTHROPIC_API_KEY` if needed (no code change).
- Product name is **ChaCha PA**. Design direction is Thread with agents as characters, minimal like
  Grok-style chat apps.
- Runs use the **Claude Pro plan login**, not API billing (also on the VPS, see the terms note above).
- Hosting: a VPS behind Cloudflare Tunnel + Access.
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
- **Decided in M9 (defaults, change if you disagree):** proposals use one sonnet call; question answers
  go into notes without a second call; a missing connector is saved as the member's `wants`, never as a tool.
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
(main only has v1; everything from M7 on is on feat/chacha-pa). First fetch the branch, then read
docs/HANDOVER.md, then AGENTS.md, then PRD section 13.

State: M1 to M8 and the M9 team builder done and tested offline (148 pytest, 46 Vitest), plus the M6 replay page, the TikTok
and ElevenLabs tools, and claude.ai connectors as team tools (found with `claude mcp list`, scoped per
agent, writes need approval). Live checks passed on 2026-11-28 (Cheap run, team proposal, team run with steering); connectors still untried live.
The app never touches logins: it runs my installed Claude Code (plan for personal use, API key for
sharing). I'm on Windows (use `python`, not `py`), and my Claude usage burns fast, so keep this
session lean and prefer cheap models.

Task: start the VPS hosting milestone (HANDOVER "What's missing" A1): first ask me which VPS
provider and OS, and remind me of the plan-login terms note. Then fix A2 (room shows the final answer
twice). Live runs work from the cloud session: keep caps low.

Follow AGENTS.md: tests for new logic, run pytest before every commit, update the docs, and list
doc changes at the end. Ask me (with options) before anything only I can decide. Push to
feat/chacha-pa; don't merge to main or open a PR unless I ask.
```
