# ChaCha PA: product requirements

## 1. Problem
Agent Orchestra already works from the command line. An orchestrator plans a task, creates its own
agents, assigns work, and loops until an independent checker passes every task. But you can only
watch it as colored log lines in a terminal on your laptop.

That makes it hard to:
- see who is doing what right now, and why a task was sent back
- start a run or check on one away from your laptop
- find old runs and their files
- show the project to anyone else

ChaCha PA is the app around the engine: type a task, press start, and watch a team of agents work,
fail, retry and finish, live, on a laptop or a phone.

## 2. Users
| User | Need |
|---|---|
| You, builder and only user | Start runs, watch them live, stop them, read results and files, from laptop or phone. |
| Portfolio viewers | Understand what the project does without access to your machine. They see a public replay page, never the app. |

## 3. Goals
1. Watching a run is clear at a glance: who is working, what passed, what failed and why.
2. Every run is verified: no task counts as done until the checker passes it.
3. Runs keep going when you close the browser, and you hear when they end.
4. The app runs on your Claude Pro plan, not API billing.
5. The app is private: never reachable by anyone else.
6. Agents can be any specialist the task needs, with tools from a catalog you control: files, web,
   a real browser, shell, MCP servers, plugins and connectors.

## 4. Non-goals (v1)
- More than one user, or sharing runs with others.
- Non-Claude models (OpenRouter comes after v1).
- A full sandbox per agent (Docker comes after v1; v1 uses the SDK's shell sandbox).
- Steering a run by chatting with the orchestrator (comes right after v1).
- A native phone app. The phone gets a responsive web app, push notifications and a widget.

## 5. User stories and acceptance criteria

### Start a run
**As you, I want to type a task and press start, so the team gets to work.**
- The new-run screen has one big text box, an Options button and a Start button.
- Start is disabled while the box is empty.
- Options: allow shell commands, repository path, models (orchestrator/workers, checker), usage cap,
  max agents. Defaults: shell off, no repo, sonnet/sonnet/haiku, $5, 6 agents.
- After Start, the run screen opens within 1 second and shows your message at the top.
- Starting a second run while one is going works. Each run has its own workspace.

### Watch it live
**As you, I want to see the orchestrator plan, hire agents and run tasks as it happens.**
- Each event shows up in the thread within 1 second of the engine logging it.
- The orchestrator's messages appear as plain text next to its character.
- A new agent appears as "<name> joined" with its character, and in the team panel.
- Each task is a card: the agent's character, a short title, one status line, attempt dots.
- While a worker is busy, one live line shows what it is doing ("analyst is reading research/dana.md").
- The usage meter, elapsed time and agent count update as the run goes.
- Closing and reopening the browser shows the full run so far, then continues live.

### See failures and retries
**As you, I want to see when the checker sends work back, and what the team does about it.**
- A failed attempt changes the card to "Try 2 · <short reason>" and the character looks worried.
- Opening the card shows "done when" and one short checker line per try.
- When a task fails all tries, its card shows Failed. If the orchestrator replaces it, the old card
  is crossed out with "Replaced by <new title>" and the new card appears.

### Approve outward actions
**As you, I want to approve anything that acts on the outside world.**
- When an agent calls a tool marked outward (send email, post a message, create an event), the run
  pauses that agent and the thread shows an Approve / Deny card with the exact action.
- A push notification is sent at the same time.
- Approve runs the action. Deny returns "denied by user" to the agent, which carries on without it.
- Read-only tools never ask.

### Stop a run
**As you, I want to stop a run at any time.**
- Stop is always visible while running. It asks for confirmation once.
- The run stops within 5 seconds. Finished tasks and written files are kept.
- The run shows "Stopped by you" in the thread and in history.

### Final result
**As you, I want a clear ending.**
- Finished: all characters happy, the orchestrator's summary, file chips, "Open <main file>".
- Out of budget: what works, what doesn't, usage used of cap, and "Continue with $X more".
- Crashed: a plain explanation and steps to fix it (for example "Your Claude login expired: run
  `claude`, then `/login`"), plus Try again.
- Interrupted (server restarted): files kept, Run again and Continue offered.

### Continue and follow up
**As you, I want to pick up where a run stopped, or build on a finished one.**
- "Continue with $X more" starts a new run that sees the old workspace files and the unfinished
  tasks, with the extra budget.
- The finished screen has a follow-up box. A follow-up run starts in a copy of the old workspace.
- Both link back to the run they came from.

### History
**As you, I want to find old runs.**
- The sidebar lists today's runs. "All runs" opens a page grouped by day.
- Search matches task text. Filters: Finished, Out of budget, Crashed, In a repo.
- Each run shows its team's faces, status, duration and usage.
- Actions: open, rerun with edits (new-run form pre-filled), download files as zip, delete
  (asks first).

### Files
**As you, I want to read what the agents made.**
- A file list shows every workspace file with the character of the agent who last wrote it.
- Markdown renders as a document, code shows as code, other text as plain text.
- Copy and Raw buttons. Download all as zip.
- On a phone, files open in a sheet from the bottom.

### Repo mode
**As you, I want agents to work on my existing project safely.**
- The run refuses to start if the folder is not a clean git repo, with a clear message.
- Work happens on a new branch `orchestra/<time>`. The branch name shows on the run screen.
- When hosted, only folders inside one allowlisted directory are accepted.

### Notifications and widget
**As you, I want to know when a run ends without keeping the app open.**
- An ntfy push goes out when a run finishes, fails, runs out of budget, or needs an approval.
- `GET /api/status` returns the current runs in a small JSON shape.
- A Scriptable script (iPhone) and a KWGT guide (Android) show a home-screen widget from it.

### Plan mode indicator
**As you, I want to be sure runs use my plan, not API billing.**
- The sidebar shows "Pro plan · plan login" when `ANTHROPIC_API_KEY` is unset, and
  "API key · billed" otherwise.

## 6. Functional requirements
| # | Requirement |
|---|---|
| F1 | Start a run with task text and options. Several runs can run at once. |
| F2 | Stream every engine event to the browser over SSE. Replay from any point. |
| F3 | Stop a run immediately. |
| F4 | Pause on outward tool calls for approval. |
| F5 | Show run history with search, filters, delete, zip download, rerun with edits. |
| F6 | Show workspace files, rendered by type. |
| F7 | Show the final result, out-of-budget, crashed and interrupted states. |
| F8 | Continue a run with more budget. Start a follow-up run from a finished one. |
| F9 | Repo mode with the clean-tree check, new branch, and allowlist when hosted. |
| F10 | Tool catalog: built-in tools, browser (Playwright MCP), MCP servers from a catalog file, local plugins, claude.ai connectors if reachable. The orchestrator can only pick from it. |
| F11 | Agents can be any role. Each gets a character color in creation order. |
| F12 | ntfy notifications and a status endpoint for widgets. |
| F13 | Plan-mode indicator. |
| F14 | Static replay page that plays back a recorded `log.jsonl`. |

## 7. Non-functional requirements
| Area | Requirement |
|---|---|
| Security | Server binds to 127.0.0.1 only. When hosted, it sits behind Cloudflare Tunnel + Cloudflare Access, plus an app token. Never exposed without auth. |
| Safety | Shell is off by default. When on, the SDK sandbox restricts commands and network. Outward tools need approval. Workers can never create agents. |
| Budget | Hard caps on agents, assignments, attempts and estimated usage, as today. The usage cap is visible on every run. |
| Billing | Default is the Pro plan login. API-key mode works without code changes. |
| Reliability | Runs survive closing the browser. A server restart marks runs `interrupted`, never silently lost. Files on disk are the source of truth. |
| Performance | Events reach the browser within 1 s. History loads 100 runs in under 300 ms. |
| Accessibility | Keyboard reachable, visible focus, 4.5:1 text contrast, one polite status region for live updates, reduced motion respected. |
| Phone | Every screen works at 390 px wide. Touch targets at least 44 px. |

## 8. From local v1 to private hosting
1. **v1, local:** the server runs on your laptop at `http://127.0.0.1:8000`. Plan login.
2. **Always-on:** the same server runs on a machine that stays on. Option A is your own machine
   (plan login stays on your device). Option B is a VPS (use an API key, per Anthropic's docs).
3. **Reach it from anywhere:** Cloudflare Tunnel gives a hostname. Cloudflare Access only lets your
   email through. The app also checks a token.
4. **Phone:** add to home screen, set up ntfy and the widget.

Nothing in v1 assumes localhost in a way that blocks step 2: paths, auth checks and the
status endpoint are all designed for it.

## 9. Success metrics
- A real run (the e-wallet report) finishes end to end in the app with every task verified.
- You can tell from the run screen alone, without logs, why any task failed.
- Starting a run from the phone takes under 15 seconds.
- No run is ever lost: every run in `runs/` appears in history with the right status.
- Zero API charges while in plan mode.

## 10. Milestones
| Milestone | Outcome |
|---|---|
| M1 Engine | Events, cancel, titles, activity, tool catalog, approvals, sandbox. CLI still works. |
| M2 Server | FastAPI with runs, SSE, files, stop, continue, status. Tested offline. |
| M3 App core | React app: new run, live run, retry, outcomes, approvals. Dark and light. |
| M4 App complete | History, files, zip, delete, rerun, follow-up, phone layouts. |
| M5 Phone extras | ntfy, status widget scripts, PWA install. |
| M6 Portfolio | Static replay page. |
| Later | Steering, Docker per agent, OpenRouter, repo diff, hosting setup. |

Details per task: [IMPLEMENTATION.md](IMPLEMENTATION.md).

## 11. Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Plan login on a server is not clearly allowed by Anthropic's terms | Could break the hosted setup | Host on your own machine, or use an API key on a VPS. Ask Anthropic if unsure. |
| Pro plan limits run out with several runs at once | Runs crash mid-way | Show the crash clearly. Suggest Max or fewer parallel runs. Usage cap per run. |
| Shell and browser act on the host machine | Damage to files or accounts | Shell off by default, SDK sandbox, outward approvals, repo allowlist, Docker later. |
| claude.ai connectors may not be reachable from the SDK | Fewer integrations | Verify in M1. Fallback: add the same services as MCP servers. |
| The checker passes weak work | False "done" | Concrete "done when" in prompts. Checker reads files, runs tests when shell is on. |
| The first live run is not tested yet | Unknown engine bugs | M1 ends with a real run before any UI work. |

## 12. Open questions
- Where to host: your own always-on machine or a VPS. Decide before the hosting milestone.
- Which MCP servers and connectors to put in the first catalog besides the browser.
