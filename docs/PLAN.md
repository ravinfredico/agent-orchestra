# Agent Orchestra UI: plan

Status: Step 0. Waiting for answers to the questions below. No docs or prototypes written yet.

## Questions

### 0. Your message was cut off
The brief ends at "Writing rules for all docs: Plain,". What are the rest of the writing rules?

### 1. Tech stack
The engine stays Python on the Claude Agent SDK, so the backend is Python in every option.

Live updates: I recommend **Server-Sent Events (SSE)** in all options. Updates only flow server to
browser. SSE reconnects by itself and resumes from `Last-Event-ID`, so a phone that drops off
wifi catches up without missing events. It also passes through reverse proxies and tunnels
without extra setup. Stop and start are plain POSTs. WebSockets would only pay off if we later
add live chat with the orchestrator.

| | A. Minimal | B. Component app (recommended) | C. Python-only |
|---|---|---|---|
| Frontend | One static `index.html`, vanilla JS, no build step | Svelte + Vite, built to static files that FastAPI serves | Server-rendered Jinja + HTMX + Alpine, HTMX SSE extension |
| Backend | FastAPI + uvicorn | FastAPI + uvicorn | FastAPI + uvicorn |
| Storage | Files only: `runs/<id>/log.jsonl`, `board.json`, `final.md` | Files stay the source of truth, plus a small SQLite index (run list, status, cost) for fast history and search | Same as B |
| Good | Matches the plan in CLAUDE.md. Nothing to install. Easy for AI agents to edit | Clean components for the many states (agent card, task row, meters). Easy to make an installable PWA for your phone (needed for web push). Stronger portfolio piece | One language. Little JS |
| Cost | One big file gets messy past about 1500 lines. Animation and state code is hand-rolled | Adds Node to the dev setup and a build step. More moving parts | Fine-grained live motion (cards animating in, meters easing) is awkward with HTML swaps. Weakest PWA story |

Alternatives to B: React + Vite (bigger ecosystem, more boilerplate) or Preact + HTM with no build
step (somewhere between A and B).

**Pick one for each:** frontend (A / B / C / other), storage (files only / files + SQLite).

### 2. Hosting (planned now, built later)

**2a. Sign-in.** Options, all keep the server off the public internet:
1. **Tailscale (recommended).** The server joins your private tailnet. Your laptop and phone reach
   it with the Tailscale app installed. No open ports and no public URL. The tailnet is the login,
   and the app adds a long random token as a second lock.
2. **Cloudflare Tunnel + Cloudflare Access.** You get a public hostname, but Cloudflare only lets
   your email through (one-time code or Google login). Works from any browser with no app, but
   Cloudflare sits in the path.
3. **Caddy reverse proxy with HTTPS + in-app passkey or password.** Fully self-run. You own all
   of the auth code, and the server is reachable from the internet.

Which one? Do you already use Tailscale or Cloudflare?

**2b. Runs keep going after you close the browser.** The plan: runs execute inside the server
process as background tasks, not tied to any browser connection. The server runs as a systemd
service (or Docker with `restart: unless-stopped`). If the server restarts mid-run, the run is
marked `interrupted`. Resuming a half-finished run is out of scope for v1. Questions:
- One run at a time, or several at once? Several at once means separate workspaces and adding
  their costs against your plan limits.
- Is "interrupted, start again" acceptable after a restart, or do you need resume?

**2c. Notifications when a run finishes or fails.** Options:
1. **ntfy** (recommended to start). Free push to the ntfy phone app, and you can self-host it. The
   server sends one HTTP POST. About 20 lines of code.
2. **Web Push from the PWA.** No extra app, but on iPhone it only works after "Add to Home
   Screen" (iOS 16.4+). Needs VAPID keys and a service worker.
3. Telegram bot, or email.
Which one? Should a failed checker attempt also notify you, or only finished/failed/out-of-budget?

**2d. Claude login on a server: what I found.**

Short version: Anthropic's docs tell developers building on the Agent SDK to use an API key, and
they make no clear exception for a single-user app on your own server. Treat using your plan
login on a server as not clearly allowed.

- Agent SDK overview: "Unless previously approved, Anthropic does not allow third party
  developers to offer claude.ai login or rate limits for their products, including agents built
  on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart
  instead." ([source](https://code.claude.com/docs/en/agent-sdk/overview))
- Legal and compliance: "OAuth authentication is intended exclusively for purchasers of Claude
  Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support
  ordinary use of Claude Code and other native Anthropic applications." And: "Developers building
  products or services that interact with Claude's capabilities, including those using the Agent
  SDK, should use API key authentication through Claude Console or a supported cloud provider."
  ([source](https://code.claude.com/docs/en/legal-and-compliance))
- The same page also says "Advertised usage limits for Pro, Max, and Ultra plans assume ordinary,
  individual usage of Claude Code and the Agent SDK", so some individual SDK use on a plan is
  expected. The page doesn't say whether a self-built web app running 24/7 on a server counts.
- Consumer Terms, section 3: automated or non-human access is prohibited "except when you are
  accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it".
  ([source](https://www.anthropic.com/legal/consumer-terms))
- The technical route exists: `claude setup-token` creates a one-year OAuth token for headless
  environments, which you set as `CLAUDE_CODE_OAUTH_TOKEN`. It ranks above a `/login` session and
  below `ANTHROPIC_API_KEY`. ([source](https://code.claude.com/docs/en/authentication)) Having the
  route doesn't make it permitted for this use.
- A search summary of the SDK docs mentions that plan usage of the SDK draws from a separate
  monthly Agent SDK credit starting June 15, 2026. I haven't confirmed this on the page itself, so
  don't rely on it yet.

My recommendation: support both auth modes from day one (plan login, or API key) and show the
active mode in the UI. Use the plan login on your laptop (v1). When you host, either use an API
key, or ask Anthropic in writing before you put your plan token on the server
([contact](https://www.anthropic.com/contact-sales)). Note: CLAUDE.md currently says
`ANTHROPIC_API_KEY` must be unset. That rule becomes "unset for plan mode" once API-key mode exists.

**Which do you want for hosting: API key, plan token after asking Anthropic, or decide later?**

### 3. Scope and priorities
1. **How much detail do you want to watch live?** Today's log only has coarse events (agent
   created, task assigned, attempt failed, passed). It doesn't capture what a worker is doing
   inside an attempt (each tool call, file written, streaming text). Capturing that means the
   runner has to forward SDK messages. It makes the live view much richer and the event log much
   bigger. Coarse only, or include per-tool-call activity?
2. **The live cost meter lags.** The orchestrator's cost only arrives when its round ends, and a
   worker's cost only arrives when its attempt ends. So the meter jumps instead of climbing. Is
   that OK for v1, or should we estimate from token usage on each message?
3. **Stop behaviour.** Hard stop (cancel now, the current attempt is lost) or graceful stop
   (finish the current attempt, then wrap up)? Or both?
4. **Mid-run interaction.** Out of scope for v1 (just start, watch, stop)? Or do you want
   "message the orchestrator" or "approve before finish"? Both appear in README's ideas.
5. **`--repo` and Bash on a hosted server.** On a server, repo paths are server paths, and Bash
   runs real commands there. Should hosted runs be limited to repos under one allowlisted folder?
   Should Bash runs go in a throwaway Docker container per run? I'd suggest an allowlisted folder
   for v1 and Docker as a later milestone.
6. **Starting runs from your phone.** Full form on the phone (all options), or a short form (task
   + preset) with advanced options folded away?
7. **History actions.** Do you need delete run, rerun with the same options, download workspace
   as a zip, or show the `--repo` diff in the UI?
8. **Portfolio viewers.** The app is never public. Would you like a separate static "replay" page
   that plays back a recorded run with no server (e.g. on GitHub Pages)? Or are screenshots and
   a video enough? This decides whether the event schema has to be replayable on its own.
9. **Name and branding.** Keep "Agent Orchestra"? Any colors, fonts or references you love or hate?
10. **Order of work.** The prototypes are static HTML with mock data and don't depend on the
    stack choice. Should I install the skills and build the 5 prototypes while you think about
    the stack and hosting questions, or wait for all answers first?

## Notes from reading the code (inputs for ARCHITECTURE.md later)
- Run ids are `%Y%m%d-%H%M%S`, so two runs started in the same second collide. Needs a suffix
  once the server can start runs.
- `prepare_repo()` prints the branch to stdout but the branch isn't stored in `RunState`, so the
  UI can't show it yet.
- No `attempt_started` or `checker_started` events, so the UI can't tell "worker running" from
  "checker running" within an attempt.
- `orchestrator.run()` blocks until the end and has no cancel hook. Crashes inside `client.query`
  aren't caught or logged.
- `RunState.log()` prints with ANSI colors, so server mode needs that switched off or redirected.
