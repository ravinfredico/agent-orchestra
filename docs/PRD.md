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
| M7 Parallel and cheaper | Independent tasks run at the same time. Each task gets the cheapest model that can do it. Usage meter per agent. See section 13. |
| M8 Teams and schedules | A saved team with its own chat room and memory, triggered by schedules, your messages and new data. See section 13. |
| M9 Team builder | Ask for any team ("a team for stocks", "a TikTok team") and ChaCha PA designs and saves it. TikTok and stocks are the first examples. See section 13. |

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

## 13. After v1: parallel agents, always-on teams, and lower cost
Added 2026-11-27. Not part of v1. Builds on everything above.

### Goals
1. **Parallel:** independent tasks run at the same time, so a run finishes sooner.
2. **Teams for anything:** you describe a team in plain words ("a team for stocks", "a TikTok
   team") and ChaCha PA designs it: members, tools, schedule, memory and outputs. The team keeps
   existing between runs, with its own chat room.
3. **Cheaper:** every task uses the cheapest model that can do it well, so your plan limits last longer.

### User stories

**Parallel agents.** As you, I want independent tasks to run side by side, so I wait less.
- The orchestrator marks which tasks depend on others. Tasks with no unfinished dependencies start
  together, up to a limit (default 3 at once).
- Two agents never write the same file at the same time. Each task names the files it owns.
- The run screen shows several "working" lines at once. Stop cancels all of them.

**Pick the right model per task.** As you, I want each task to use the cheapest model that can do it.
- The orchestrator picks a tier for each agent and task: haiku for search, reading, summaries,
  simple edits and checks; sonnet for writing, planning and code; opus only when a task has failed on
  sonnet. The pick and the reason are shown on the task card.
- If a task fails on its tier, the retry moves up one tier, once.
- You can override the tier for a team or a run.

**Ask for any team.** As you, I want to say "I want a team for stocks" and get one.
- You describe the goal in one message. The orchestrator proposes a team: members and their roles,
  the tools each needs from the catalog, a schedule, what it produces, and which actions need your
  approval. It asks you about anything unclear (for example which stocks, or how often).
- You review the proposal, change it if you like, and save it. Nothing runs until you save.
- If the team needs a tool that isn't in the catalog yet (for example a market-data API or TikTok
  posting), the proposal says so and lists what to set up. Agents still never invent tools.
- Teams can be edited later: add a member, change the schedule, change model tiers.
- Examples to ship with, to show the range:
  - **TikTok team:** research, scripts, rendered videos, posting with approval, learning from stats
    (details below).
  - **Stocks team:** a watchlist you set, a daily brief (news, price moves, earnings dates), deeper
    research notes on request, alerts when something big happens. It never trades. Any action
    with money stays outside the app, and briefs say they are not financial advice.

**A team room.** As you, I want a saved team I can chat with like a group chat.
- A team has a name, members (agents with roles, tools and model tiers), a memory, and a room.
- The room shows your messages, the agents' replies, and the agents talking to each other while they
  work (pitches, critiques, hand-offs). You can jump in at any point.
- The team remembers past work and your feedback ("no more cooking videos") in a memory file it
  reads before each job, so it doesn't redo research.

**Always on, without burning usage.** As you, I want the team to keep working without me.
- The team is always available, but only spends usage when something triggers it:
  - a schedule slot (for example 09:00 and 18:00 every day)
  - a message from you in the room
  - new data (for example fresh post stats)
- Between triggers it sleeps and costs nothing.
- Each trigger runs as a normal verified run, linked to the team, so history, files and stops work
  as today.
- It only runs while the machine hosting ChaCha PA is on (your laptop now, a host later).

**Example: AI TikTok team.** As you, I want a team that makes and posts TikTok videos and learns what works.
- **Research and scripts:** trends, ideas, hooks, scripts, captions, hashtags, saved as files.
- **Finished videos:** short vertical videos rendered with Remotion plus a voiceover, like the demo video.
- **Post to TikTok:** uploads or schedules posts. Every post waits for your approval (outward action).
- **Performance review:** reads views, likes and watch time of past posts and writes what to do more or less of.

### Requirements
| # | Requirement |
|---|---|
| F15 | Parallel task execution with dependencies, a concurrency limit, and file ownership per task. |
| F16 | Model tier per agent and per task, chosen by the orchestrator, with one automatic step up on failure. |
| F17 | Usage per agent, per task and per model, shown on the run and team pages. |
| F18 | Cheap checks first: when a "done when" can be checked by a command (file exists, tests pass), run it without a model. Use the model checker only for what a command can't judge. |
| F19 | Teams: saved members, memory file, room (chat) with your messages and agent-to-agent messages. |
| F20 | Triggers: schedules (cron-like), room messages, and data webhooks. Each trigger starts a linked run. |
| F21 | Team budget: usage per day and per trigger. A trigger that would go over is skipped and you get a push. (Recommended; not yet decided, see open questions.) |
| F22 | Team builder: from one message, propose a team (members, tools, tiers, schedule, outputs, approvals), ask about gaps, save on your OK. |
| F23 | Missing tools are listed in the proposal as setup steps, never invented. |
| F24 | Example team connectors: TikTok posting (with approval) and stats; market data and news for the stocks team. |

### Ways to keep it cheap
- Right model per task (F16). This is the biggest saving.
- Cheap checks before model checks (F18).
- Team memory, so research isn't repeated every run.
- Pass file paths to agents, not whole file contents, and keep worker steps low for simple tasks.
- Batch work: one scheduled run makes several videos, instead of one run each.
- Sleep between triggers. Never loop on a timer with nothing to do.

### Risks
| Risk | Impact | Mitigation |
|---|---|---|
| "Always on" on a Claude plan uses up the 5-hour and weekly limits | Runs stop mid-way, other Claude use blocked | Triggers only, cheap models, team budget. Consider an API key for teams. |
| Anthropic's terms for automated, continuous use of a plan login | Account risk | Check the terms before always-on use on a plan. The Agent SDK docs point to API keys for products. |
| TikTok API access needs a registered developer app, and posting may need TikTok's review (unreviewed apps may only post privately) | Posting not possible at first | Start with drafts you post yourself. Apply for access early. Check TikTok's current rules. |
| Parallel agents edit the same file | Lost work | File ownership per task; the orchestrator is told to split files. |
| Agents talking to each other burn tokens | Higher usage | Keep agent-to-agent messages short and only at hand-offs; show them from the event log. |
| Posting content you didn't review | Reputation | Every post needs approval, always. |
| A stocks team's output is taken as financial advice, or tries to trade | Money loss | No trading tools in the catalog. Briefs say they are not financial advice. |
| Teams need paid data APIs (market data, TikTok) | Extra cost and setup | The team builder lists what each team needs before you save it. |

### Open questions
- Hard daily usage cap for teams, or only model routing? (You chose routing; a cap is recommended as a safety net.)
- Which machine runs the always-on team: your laptop (must stay on) or a host?
- Plan login or an API key for teams?
- TikTok account type and API access (developer app, posting review).
- Stocks team: which markets (for example IDX, US), and which data source (free with delays, or paid).
