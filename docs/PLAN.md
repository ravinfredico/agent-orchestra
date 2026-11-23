# ChaCha PA: plan and decisions

ChaCha PA is the web app for Agent Orchestra. You type a task, press start, and watch the
orchestrator hire agents, assign tasks, retry and finish, live.

Status: M1 to M4 built on branch `feat/chacha-pa` and tested offline. Next: the first live run, then
M5 and M6 in [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Documents
| Doc | What it holds |
|---|---|
| [PRD.md](PRD.md) | Problem, users, goals, user stories, requirements, milestones, risks |
| [DESIGN.md](DESIGN.md) | Screens, component states, tokens, motion, copy, accessibility |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Stack, API, live event schema, refactors, persistence, hosting |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Milestones, tasks, acceptance criteria, tests, first live test |

Design canvas (private to you): https://claude.ai/artifact/1VhNwtUMKpMpNrVvbyhNUS

## Decisions
| Topic | Decision |
|---|---|
| Name | ChaCha PA. Repo and Python package keep their names (`agent-orchestra`, `orchestra`). |
| Design | "Thread" direction: a monochrome chat where agents are colored characters whose faces show their status. |
| Frontend | React 19 + Vite + TypeScript, built to static files that FastAPI serves. |
| Backend | FastAPI + uvicorn. |
| Live updates | Server-Sent Events, with replay from `Last-Event-ID`. |
| Storage | `runs/<id>/` files are the source of truth. A SQLite index (`runs/index.db`) speeds up history and can be rebuilt from the files. |
| Billing | Runs use your Claude Pro plan login with `ANTHROPIC_API_KEY` unset. API-key mode is also supported. The UI shows which mode is active. |
| Sign-in when hosted | Cloudflare Tunnel + Cloudflare Access. |
| Where it is hosted | Decided later: your own always-on machine (keeps the plan login on your device) or a VPS (should use an API key, see below). |
| Concurrency | Several runs at once, each with its own workspace. |
| Server restart | Running runs are marked `interrupted`. Files are kept. |
| Stop | Cancels immediately. Finished tasks and files are kept. |
| Notifications | ntfy push on finished, failed and out of budget. Home-screen widget for iPhone (Scriptable) and Android (KWGT), reading `GET /api/status`. |
| Live detail | Task and agent events plus one live activity line per worker. |
| Usage meter | Updates when an attempt or orchestrator round ends. It jumps instead of climbing, which is fine for v1. |
| Repo and shell when hosted | Repos only from one allowlisted folder. Docker sandbox per run comes later. |
| History actions | Delete, download as zip, rerun with edits. Repo diff comes later. |
| Extras from the designs | Short task `title` on `assign_task`. "Continue with more budget". Follow-up run box. Plan-mode indicator. |
| Agents | Any role the task needs. No role templates: the orchestrator invents each specialist, writes its prompt, and picks its tools from the catalog. |
| First connectors | Gmail and Google Calendar. Claude Code plugins can be picked per run. |
| Tool catalog | The orchestrator can only give agents tools from a catalog: built-in tools, MCP servers listed in a project catalog file (local or remote, each with a description and a risk level), local Claude Code plugins, and claude.ai connectors if the SDK can reach them (to verify in M1; otherwise the same services go in as MCP servers). |
| Browser | A browser (Playwright MCP) is in the catalog by default, so agents can open and use real web pages. |
| Isolation | v1: the SDK's built-in shell sandbox with a network allowlist, plus one folder per agent. Later: a Docker container per agent, sharing a `/workspace` volume for handoffs. |
| Outward actions | Tools that act on the outside world (send email, post, book) pause the run and show an Approve / Deny card, plus a push notification. Read-only tools run freely. |
| Model providers | Claude only in v1, on your Pro plan. OpenRouter later, through a gateway. It needs its own API key and is billed by OpenRouter. |
| After v1 | Message the orchestrator mid-run, then Docker sandbox per agent, OpenRouter models, repo diff, hosting setup. |
| Portfolio | Static replay page (GitHub Pages) that plays back a recorded run. |
| Writing | Plain English, short sentences, no jargon or filler, lists and tables where they help. |

## Claude plan login on a server: what we found
- Agent SDK overview: "Unless previously approved, Anthropic does not allow third party developers to
  offer claude.ai login or rate limits for their products, including agents built on the Claude Agent
  SDK." ([source](https://code.claude.com/docs/en/agent-sdk/overview))
- Legal and compliance: developers building with the Agent SDK "should use API key authentication".
  The same page says plan limits "assume ordinary, individual usage of Claude Code and the Agent SDK".
  ([source](https://code.claude.com/docs/en/legal-and-compliance))
- Consumer Terms, section 3: automated access is not allowed "except when you are accessing our
  Services via an Anthropic API Key or where we otherwise explicitly permit it".
  ([source](https://www.anthropic.com/legal/consumer-terms))
- `claude setup-token` makes a one-year token for headless use (`CLAUDE_CODE_OAUTH_TOKEN`).
  ([source](https://code.claude.com/docs/en/authentication)) That a way exists does not make it allowed.

What we do: plan login on your laptop and on your own always-on machine. On a rented server, use an
API key or get written approval from Anthropic first.

## Notes from reading the code
These feed the refactors in ARCHITECTURE.md.
- Run ids are `%Y%m%d-%H%M%S`, so two runs started in the same second collide.
- `prepare_repo()` prints the branch name but `RunState` does not store it.
- No `attempt_started` or `checker_started` events.
- `orchestrator.run()` blocks until the end, has no cancel hook, and does not log crashes.
- `RunState.log()` prints ANSI colors to stdout.
