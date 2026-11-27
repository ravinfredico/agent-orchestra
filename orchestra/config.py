"""Run configuration: models and budget guardrails."""

from dataclasses import asdict, dataclass, field

# Model tiers, cheapest first. A failed task retries one tier up, once, up to `max_tier`.
TIERS = ["haiku", "sonnet", "opus"]


def tier_rank(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else TIERS.index("sonnet")


def step_up(tier: str, max_tier: str) -> str | None:
    """The next tier up, or None if `tier` is already at `max_tier` (or the top)."""
    nxt = tier_rank(tier) + 1
    return TIERS[nxt] if nxt < len(TIERS) and nxt <= tier_rank(max_tier) else None


def clamp_tier(tier: str, max_tier: str) -> str:
    return TIERS[min(tier_rank(tier), tier_rank(max_tier))]


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
    worker_model: str = "sonnet"        # default tier when the orchestrator names none
    pick_tier: bool = True              # the orchestrator picks a tier per agent and task
    max_tier: str = "opus"              # highest tier a pick or a step-up may reach
    checker_model: str = "haiku"
    allow_bash: bool = False
    budget: Budget = field(default_factory=Budget)
    catalog: list[str] | None = None    # catalog ids allowed for this run; None = every enabled entry
    allowed_domains: list[str] = field(default_factory=list)  # network allowlist for sandboxed shell
    playbook: str = "auto"            # playbook id, or "auto" to let the orchestrator pick

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
            "pick_tier": self.pick_tier,
            "max_tier": self.max_tier,
            "max_steps": b.max_worker_turns,
            "max_cost": b.max_cost_usd,
            "max_agents": b.max_agents,
            "max_assignments": b.max_assignments,
            "max_attempts": b.max_attempts_per_task,
            "catalog": self.catalog,
            "allowed_domains": self.allowed_domains,
            "playbook": self.playbook,
        }

    @classmethod
    def from_options(cls, o: dict | None) -> "Config":
        o = o or {}
        return cls(
            orchestrator_model=o.get("orchestrator_model") or "sonnet",
            worker_model=o.get("worker_model") or "sonnet",
            checker_model=o.get("checker_model") or "haiku",
            pick_tier=bool(o.get("pick_tier", True)),
            max_tier=o.get("max_tier") if o.get("max_tier") in TIERS else "opus",
            allow_bash=bool(o.get("allow_bash", False)),
            catalog=o.get("catalog") or None,
            allowed_domains=list(o.get("allowed_domains") or []),
            playbook=o.get("playbook") or "auto",
            budget=Budget(
                max_agents=int(o.get("max_agents", 6)),
                max_assignments=int(o.get("max_assignments", 15)),
                max_attempts_per_task=int(o.get("max_attempts", 3)),
                max_worker_turns=int(o.get("max_steps", 25)),
                max_cost_usd=float(o.get("max_cost", 5.0)),
            ),
        )


__all__ = ["Budget", "Config", "CHECKER_TOOLS", "TIERS", "asdict", "clamp_tier", "step_up", "tier_rank"]
