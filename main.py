"""CLI entry point.

    python main.py "Research the top 5 Indonesian e-wallets and write a comparison report"
"""

import argparse
import asyncio
from pathlib import Path

from orchestra.config import Budget, Config
from orchestra.gitsafe import RepoError, prepare_repo
from orchestra.orchestrator import run


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-agent orchestrator on the Claude Agent SDK")
    p.add_argument("task", nargs="?", help="The task to give the orchestrator")
    p.add_argument("-f", "--task-file", type=Path, help="Read the task from a file instead")
    p.add_argument("--allow-bash", action="store_true", help="Let agents run shell commands (needed for code + tests)")
    p.add_argument("--orchestrator-model", default="sonnet")
    p.add_argument("--worker-model", default="sonnet")
    p.add_argument("--checker-model", default="haiku")
    p.add_argument("--max-agents", type=int, default=6)
    p.add_argument("--max-assignments", type=int, default=15)
    p.add_argument("--max-attempts", type=int, default=3, help="Retries per task")
    p.add_argument("--max-cost", type=float, default=5.0, help="Estimated USD of usage before wrapping up")
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--repo", type=Path, help="Work on an existing git repo (on a new branch) instead of an empty folder")
    p.add_argument("--allow-dirty", action="store_true", help="Allow --repo with uncommitted changes")
    a = p.parse_args()
    if not a.task and not a.task_file:
        p.error("give a task or --task-file")
    return a


def main() -> None:
    a = parse_args()
    task = a.task_file.read_text() if a.task_file else a.task
    config = Config(
        orchestrator_model=a.orchestrator_model,
        worker_model=a.worker_model,
        checker_model=a.checker_model,
        allow_bash=a.allow_bash,
        budget=Budget(
            max_agents=a.max_agents,
            max_assignments=a.max_assignments,
            max_attempts_per_task=a.max_attempts,
            max_cost_usd=a.max_cost,
        ),
    )
    workspace = None
    if a.repo:
        try:
            prepare_repo(a.repo, a.allow_dirty)
        except RepoError as e:
            raise SystemExit(f"Error: {e}")
        workspace = a.repo.resolve()

    state = asyncio.run(run(task, config, a.runs_dir, workspace))

    u = state.usage
    print("\n" + "=" * 60)
    print(state.final_result)
    print("=" * 60)
    print(f"Agents: {len(state.agents)}  Tasks: {len(state.board)}  "
          f"Model calls: {u.model_calls}  Turns: {u.turns}  Est. cost: ${u.cost_usd:.2f}")
    print(f"Output files: {state.workspace}")
    print(f"Logs: {state.run_dir / 'log.jsonl'}")


if __name__ == "__main__":
    main()
