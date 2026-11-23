# Agent Orchestra UI: plan

Status: Step 0 and Step 1. The design skills are installed. The design directions are being explored in a
Claude Design artifact; the chosen one will then be built in Figma. Docs wait for the answers below.

## Decisions so far
- Design happens in a design tool first: a Claude Design artifact for the 5 directions, then Figma for
  the chosen one. No hand-written HTML prototypes.
- Design skills `ui-ux-pro-max` and `emil-design-eng` are installed in `.claude/skills/` and committed.
- Questions live in this file.
- Direction: Thread, with agents as characters (canvas: https://claude.ai/artifact/1VhNwtUMKpMpNrVvbyhNUS).
  Task cards stay minimal, which needs a short `title` field on `assign_task`.
- Billing: runs use your Claude Pro plan login, not API billing. `ANTHROPIC_API_KEY` stays unset and
  the UI shows that plan mode is active. For hosting, the preferred path is an always-on machine of
  your own, reached over Tailscale, so the plan login stays on your own device (see 2d).

## Open questions

### 0. Writing rules
Your brief ends at "Writing rules for all docs: Plain,". What is the rest?

### 1. Tech stack
The engine stays Python on the Claude Agent SDK, so the backend is Python in every option. For live
updates I recommend **Server-Sent Events (SSE)** in all options:
- Updates only flow from server to browser.
- SSE reconnects by itself and resumes from `Last-Event-ID`, so a phone that drops off wifi catches up.
- It passes through reverse proxies and tunnels without extra setup.

Stop and start are plain POSTs.

| | A. Minimal | B. Component app (recommended) | C. Python-only |
|---|---|---|---|
| Frontend | One static `index.html`, vanilla JS, no build step | Svelte + Vite, built to static files that FastAPI serves | Jinja + HTMX + Alpine, HTMX SSE extension |
| Backend | FastAPI + uvicorn | FastAPI + uvicorn | FastAPI + uvicorn |
| Storage | Files only: `runs/<id>/log.jsonl`, `board.json`, `final.md` | Files stay the source of truth, plus a small SQLite index for history | Same as B |
| Good | Matches CLAUDE.md. Nothing to install | Clean components for the many states. Easy installable phone app (PWA). Stronger portfolio piece | One language, little JS |
| Cost | One big file gets messy. Animation code is hand-rolled | Adds Node and a build step | Fine-grained live motion is awkward. Weakest PWA story |

**Pick:** frontend (A / B / C / other) and storage (files only / files + SQLite).

### 2. Hosting (planned now, built later)
**2a. Sign-in.** All of these keep the server off the public internet:
1. **Tailscale (recommended).** No open ports and no public URL. Your laptop and phone join your
   private network, and the app adds a long token as a second lock.
2. **Cloudflare Tunnel + Cloudflare Access.** Works from any browser with no app. Cloudflare checks
   your email, and it sits in the path of your traffic.
3. **Caddy + HTTPS + in-app passkey or password.** Fully self-run. You own the auth code, and the
   server is reachable from the internet.

Which one? Do you already use Tailscale or Cloudflare?

**2b. Runs keep going after you close the browser.** Runs execute inside the server process, not tied
to any browser connection. The server runs as a systemd service. If the server restarts mid-run, the
run is marked `interrupted`.
- One run at a time, or several at once?
- Is "interrupted, start again" acceptable, or do you need resume?

**2c. Notifications.**
- Options:
  - ntfy (recommended: one HTTP POST, self-hostable)
  - Web Push from the installed phone app (on iPhone it needs "Add to Home Screen")
  - Telegram or email
- Notify on finished/failed/out-of-budget only, or also on every failed attempt?

**2d. Claude login on a server.** Anthropic's docs tell developers building on the Agent SDK to use an
API key. They make no clear exception for a single-user app on your own server, so treat using your
plan login on a server as not clearly allowed.
- Agent SDK overview: "Unless previously approved, Anthropic does not allow third party developers to
  offer claude.ai login or rate limits for their products, including agents built on the Claude Agent
  SDK. Use the API key authentication methods described in the Quickstart instead."
  ([source](https://code.claude.com/docs/en/agent-sdk/overview))
- Legal and compliance: "Developers building products or services that interact with Claude's
  capabilities, including those using the Agent SDK, should use API key authentication through Claude
  Console or a supported cloud provider." The same page says "Advertised usage limits for Pro, Max,
  and Ultra plans assume ordinary, individual usage of Claude Code and the Agent SDK", so some
  individual SDK use on a plan is expected. ([source](https://code.claude.com/docs/en/legal-and-compliance))
- Consumer Terms, section 3: automated access is prohibited "except when you are accessing our
  Services via an Anthropic API Key or where we otherwise explicitly permit it".
  ([source](https://www.anthropic.com/legal/consumer-terms))
- The technical route exists. `claude setup-token` makes a one-year token for headless use, set as
  `CLAUDE_CODE_OAUTH_TOKEN`. ([source](https://code.claude.com/docs/en/authentication)) That a route
  exists doesn't make it permitted.
- Unconfirmed: a search summary mentions that plan usage of the SDK draws from a separate monthly
  Agent SDK credit from June 15, 2026. I haven't seen this on the page itself.

Recommendation:
- Support both modes (plan login or API key) and show the active mode in the UI.
- Use the plan login on your laptop.
- When hosting, use an API key, or ask Anthropic in writing first
  ([contact](https://www.anthropic.com/contact-sales)).

**Which for hosting: API key, plan token after asking Anthropic, or decide later?**

### 3. Scope and priorities
1. **Detail level.** Today's log has coarse events only. Should you see each worker's tool calls and
   file writes live? It's richer, and the log gets much bigger.
2. **Cost meter lag.** Cost arrives only when an orchestrator round or a worker attempt ends, so the
   meter jumps. Is that OK for v1, or should we estimate per message?
3. **Stop.** Cancel now, let the current attempt finish, or both?
4. **Mid-run interaction.** Is v1 just start, watch and stop, or do you want "message the
   orchestrator" or "approve before finish"?
5. **`--repo` and Bash on a server.** Allowlist one repos folder for v1, and add a Docker container per
   run later?
6. **Starting from your phone.** The full form, or task + preset with advanced options folded away?
7. **History actions.** Delete, rerun with the same options, download as zip, show the repo diff?
8. **Portfolio viewers.** A separate static replay page with no server, or screenshots and video?
9. **Branding.** Keep "Agent Orchestra"? Any colors or fonts you love or hate?

### 4. Design direction
1. **Which concepts to explore.** Here are 5 proposals. Keep them, swap some, or add your own:
   - **Score:** the run as a timeline. Each agent is a lane, attempts are bars, and passes and fails
     are marked.
   - **Control Room:** a dense, keyboard-first terminal layout with panes for agents, board and log.
   - **Studio:** a board where agents are characters and task cards move between columns
     (queued, working, checking, done).
   - **Thread:** the run reads as a chat. The orchestrator, agents and checker post, and task cards
     update in place.
   - **Blueprint:** a live system diagram where tasks travel as packets between orchestrator,
     agents, checker and workspace, and failures loop back.
2. **References.** Any products, sites or styles you like or dislike? For example Linear, Vercel,
   Raycast, Arc, terminal UIs, editorial magazines.
3. **What you didn't like** about the first HTML attempt (the "Score" direction): the concept, the
   look, or the way it was delivered?
4. **Motion in the design phase.** Static frames for each state, or a clickable prototype in the
   design tool?

## Notes from reading the code (inputs for ARCHITECTURE.md later)
- Run ids are `%Y%m%d-%H%M%S`, so two runs in the same second collide. Needs a suffix.
- `prepare_repo()` prints the branch, but `RunState` doesn't store it, so the UI can't show it.
- There are no `attempt_started` or `checker_started` events, so the UI can't tell "worker running"
  from "checker running".
- `orchestrator.run()` blocks until the end with no cancel hook. Crashes inside `client.query` aren't
  caught or logged.
- `RunState.log()` prints ANSI colors, so server mode needs that switched off or redirected.
