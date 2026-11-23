"""Run configuration: models and budget guardrails."""

from dataclasses import asdict, dataclass, field

# Tools the checker uses to inspect work. Read-only on purpose (plus Bash when shell is allowed).
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
    catalog: list[str] | None = None    # catalog ids allowed for this run; None = every enabled entry
    allowed_domains: list[str] = field(default_factory=list)  # network allowlist for sandboxed shell

    def checker_tools(self) -> list[str]:
        # With Bash allowed, the checker can run tests to verify for real.
        return CHECKER_TOOLS + (["Bash"] if self.allow_bash else [])

    def to_options(self) -> dict:
        b = self.budget
        return {
            "allow_bash": self.allow_bash,
            "orchestrator_model": self.orchestrator_model,
            "worker_model": self.worker_model,
            "checker_model": self.checker_model,
            "max_cost": b.max_cost_usd,
            "max_agents": b.max_agents,
            "max_assignments": b.max_assignments,
            "max_attempts": b.max_attempts_per_task,
            "catalog": self.catalog,
            "allowed_domains": self.allowed_domains,
        }

    @classmethod
    def from_options(cls, o: dict | None) -> "Config":
        o = o or {}
        return cls(
            orchestrator_model=o.get("orchestrator_model") or "sonnet",
            worker_model=o.get("worker_model") or "sonnet",
            checker_model=o.get("checker_model") or "haiku",
            allow_bash=bool(o.get("allow_bash", False)),
            catalog=o.get("catalog") or None,
            allowed_domains=list(o.get("allowed_domains") or []),
            budget=Budget(
                max_agents=int(o.get("max_agents", 6)),
                max_assignments=int(o.get("max_assignments", 15)),
                max_attempts_per_task=int(o.get("max_attempts", 3)),
                max_cost_usd=float(o.get("max_cost", 5.0)),
            ),
        )


__all__ = ["Budget", "Config", "CHECKER_TOOLS", "asdict"]
