# Agent Orchestra

Multi-agent orchestration harness on the Claude Agent SDK (Python). An orchestrator agent plans a task,
creates its own worker agents at runtime (writes their system prompts, picks tools from a fixed
registry), assigns tasks with a concrete `done_when`, and loops until an independent checker passes
every task. Runs on the user's Claude plan via Claude Code login (ANTHROPIC_API_KEY must be unset).

## Layout
- `main.py` CLI entry
- `orchestra/config.py` models, `Budget` limits, worker `TOOL_REGISTRY`
- `orchestra/prompts.py` orchestrator + checker prompts, checker JSON schema
- `orchestra/runner.py` `run_agent()`: one agent via `claude_agent_sdk.query()`
- `orchestra/tools.py` `OrchestraTools`: create_agent / assign_task (inner retry+verify loop) / view_board / finish, exposed as an in-process MCP server `orchestra`
- `orchestra/orchestrator.py` outer loop with `ClaudeSDKClient`, nudges until `finish` is accepted
- `orchestra/state.py` `RunState`: agents, task board, usage, `log()` to `runs/<ts>/log.jsonl`
- `orchestra/gitsafe.py` `--repo` safety: clean git tree required, works on branch `orchestra/<ts>`

## The loops
1. Agent loop: handled by the SDK per agent
2. Inner loop (`assign_task`): worker attempt -> checker (read-only tools, + Bash if allowed) -> feedback -> retry, up to `max_attempts_per_task`
3. Outer loop (`orchestrator.py`): orchestrator replans on FAILED; `finish` refuses while tasks are unfinished; a new task can supersede a failed one via `replaces`

## Conventions
- Handlers in `OrchestraTools` are plain async functions so they can be tested with a fake runner
- Workers can never create agents. Orchestrator has no built-in tools (`tools=[]`)
- All agents use `permission_mode="dontAsk"` and `setting_sources=[]`
- Use model aliases (`sonnet`, `haiku`) not dated model IDs

## Commands
- `pip install -r requirements.txt`
- `python -m pytest tests -q` (offline, no model calls)
- `python main.py "task"` / `python main.py --allow-bash --repo PATH "task"`

## Status
- Offline tests pass. Not yet verified end to end against a real model. First live run is the real test.

## Next: local web UI
Goal: type a task in a browser, press start, watch it run live. Planned design:
- Backend: FastAPI + uvicorn, `server.py`. Endpoints: `POST /api/runs` (task + options, starts run as a background asyncio task), `GET /api/runs` (history from `runs/`), `GET /api/runs/{id}/events` (SSE: replay `log.jsonl`, then live), `GET /api/runs/{id}` (board + final), `GET /api/runs/{id}/files` and file content, `POST /api/runs/{id}/stop` (cancel task).
- Needed refactors: add event listeners to `RunState.log()` for SSE; emit a `usage` event from `record_usage()`; emit `attempt_started` in the inner loop; split `orchestrator.run()` into create-state and execute so the server gets the run id immediately; catch crashes and log an `error` event.
- Frontend: single static `index.html` (vanilla JS, no build step). Sidebar: new run form (task, allow bash, repo path, models, max cost, max agents) + run history. Main: usage meters, agents panel (appear live with tools), task board (status per task, attempts, checker feedback), event log, final result, workspace files viewer.
- Bind to 127.0.0.1 only. Bash-enabled runs execute real commands on this machine.
