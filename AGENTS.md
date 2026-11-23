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
| `orchestra/config.py` | models, `Budget` limits, tool registry (moving to `catalog.py`) |
| `orchestra/prompts.py` | orchestrator and checker prompts, checker JSON schema |
| `orchestra/runner.py` | `run_agent()`: one agent via `claude_agent_sdk.query()` |
| `orchestra/tools.py` | `OrchestraTools`: create_agent, assign_task (inner loop), view_board, finish, as in-process MCP server `orchestra` |
| `orchestra/orchestrator.py` | outer loop with `ClaudeSDKClient` |
| `orchestra/state.py` | `RunState`: agents, board, usage, `log()` to `runs/<id>/log.jsonl` |
| `orchestra/gitsafe.py` | `--repo` safety: clean tree, branch `orchestra/<ts>` |
| `server/` (planned) | FastAPI app, RunManager, SQLite index, ntfy |
| `web/` (planned) | React + Vite + TypeScript app |
| `tools.catalog.json` (planned) | tools the orchestrator may give agents |

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
python -m pytest tests -q                      # offline, no model calls
python main.py "task"                          # CLI run
python main.py --allow-bash --repo PATH "task" # coding task on an existing repo
```
Planned: `python -m server` (API on 127.0.0.1:8000), `cd web && npm run dev` / `npm test` / `npm run build`.

## Conventions
- Handlers in `OrchestraTools` are plain async functions, so tests can use a fake runner.
- Workers can never create agents. The orchestrator has no built-in tools (`tools=[]`).
- Agents only get tools from the catalog. Never let the orchestrator invent tools.
- All agents use `setting_sources=[]`. Use `permission_mode="dontAsk"`, except agents with outward
  tools, which use the approval callback.
- Use model aliases (`sonnet`, `haiku`, `opus`), not dated model IDs.
- Events: one envelope `{seq, run_id, t, type, ...}`, defined in `docs/ARCHITECTURE.md` section 7.
  A new event type needs an entry there and a row in the event-to-UI map in `docs/DESIGN.md`.
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
- Engine: offline tests pass. Not yet run end to end against a real model. The first live run is
  part of M1.
- Design: done. Thread direction with agents as characters. Canvas linked in `docs/DESIGN.md`.
- Docs: PRD, DESIGN, ARCHITECTURE, IMPLEMENTATION written.
- Next: M1 (engine refactors and events) in `docs/IMPLEMENTATION.md`.

## Learnings
- Design work goes into a design tool (Claude Design canvas, then Figma) before any HTML. No
  hand-built HTML prototypes.
- Ask the user open questions directly, with concrete options for each, rather than listing them
  in a doc.
- Check with the user before touching Figma: the connected Figma account is not theirs.
