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
- `server.py` + `web/index.html` local web UI

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
- `python server.py` then open http://127.0.0.1:8000

## Status
- Offline tests pass (23). Web UI verified in a real browser against a simulated orchestrator.
- Not yet verified end to end against a real model. First live run (CLI or UI) is the real test.

## Web UI (`server.py` + `web/index.html`)
- `create_app(runs_dir, execute=...)`; `execute` is injectable so `tests/test_server.py` runs offline
- Runs start as background asyncio tasks: `orchestrator.create_state()` (run id at once) then `execute()`
- Live events: `RunState.listeners` get every `log()` entry; entries carry `seq`, SSE uses it for replay+live without gaps and for `Last-Event-ID` reconnects. Stream ends with `run_end`
- Frontend renders panels from `GET /api/runs/{id}` (refetched on events, debounced) and the log from SSE
- Middleware rejects non-local Host/Origin and non-JSON POSTs (DNS rebinding / cross-site POST). Bind stays 127.0.0.1
- `RunState.status`: running | finished | gave_up | incomplete | error | stopped (`interrupted` = server died mid-run)
