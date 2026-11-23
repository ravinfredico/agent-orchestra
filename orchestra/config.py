"""Run configuration: models, budget guardrails, and the worker tool registry."""

from dataclasses import dataclass, field


# Built-in Claude Code tools a worker agent may be given.
# The orchestrator can only pick from this list. It can never invent tools.
TOOL_REGISTRY: dict[str, str] = {
    "Read": "Read files in the workspace",
    "Write": "Create or overwrite files in the workspace",
    "Edit": "Make targeted edits to existing files",
    "Glob": "Find files by name pattern",
    "Grep": "Search file contents",
    "WebSearch": "Search the web",
    "WebFetch": "Fetch and read a web page",
}

# Only added to the registry when you pass --allow-bash.
BASH_TOOL = {"Bash": "Run shell commands in the workspace (scripts, tests, installs)"}

# Tools the checker uses to inspect work. Read-only on purpose.
CHECKER_TOOLS = ["Read", "Glob", "Grep"]


@dataclass
class Budget:
    """Hard limits for one run. When any is hit, the run wraps up."""

    max_agents: int = 6                 # agents the orchestrator may create
    max_assignments: int = 15           # assign_task calls in total
    max_attempts_per_task: int = 3      # inner retry loop per assignment
    max_worker_turns: int = 25          # tool-use turns per worker attempt
    max_orchestrator_turns: int = 60    # orchestrator turns per session
    max_nudges: int = 3                 # times we push the orchestrator to keep going
    max_cost_usd: float = 5.0           # estimated cost across the whole run


@dataclass
class Config:
    orchestrator_model: str = "sonnet"
    worker_model: str = "sonnet"
    checker_model: str = "haiku"
    allow_bash: bool = False
    budget: Budget = field(default_factory=Budget)

    def tool_registry(self) -> dict[str, str]:
        reg = dict(TOOL_REGISTRY)
        if self.allow_bash:
            reg.update(BASH_TOOL)
        return reg

    def checker_tools(self) -> list[str]:
        # With Bash allowed, the checker can run tests to verify for real.
        return CHECKER_TOOLS + (["Bash"] if self.allow_bash else [])
