"""Scripted stand-ins for the model, for offline tests and the server's demo mode.

Never used unless asked for: tests import it directly, and the server only uses it when started
with ORCHESTRA_FAKE_RUNNER=1. No model is called and nothing is billed.

    runner = FakeRunner({"[research]": FakeTask(verdicts=[True], files=[("a.md", "# A")])})
    client_factory = fake_client_factory(script)   # script: async generator using the tools
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from .catalog import BUILTIN_ENTRIES, Catalog, Entry, _entry_from_dict
from .runner import AgentResult


@dataclass
class FakeTask:
    """What happens each time a worker gets a task whose text contains this key."""
    verdicts: list[bool] = field(default_factory=lambda: [True])
    reasons: list[str] = field(default_factory=list)       # checker reason per attempt
    shorts: list[str] = field(default_factory=list)        # checker short per attempt
    files: list[tuple[str, str]] = field(default_factory=list)
    tools: list[tuple[str, dict]] = field(default_factory=list)
    outward: tuple[str, dict] | None = None                # (tool_name, input) to ask approval for
    cost: float = 0.2
    attempts: int = 0


class FakeRunner:
    def __init__(self, tasks: dict[str, FakeTask], delay: float = 0.0, checker_cost: float = 0.05):
        self.tasks = tasks
        self.delay = delay
        self.checker_cost = checker_cost
        self.calls = {"worker": 0, "checker": 0}
        self.prompts: list[str] = []

    def _find(self, prompt: str) -> FakeTask:
        for key, t in self.tasks.items():
            if key in prompt:
                return t
        return FakeTask()

    async def __call__(self, *, prompt, output_schema=None, cwd=None, on_tool_use=None, can_use_tool=None, **kw):
        t = self._find(prompt)
        if output_schema:  # checker
            self.calls["checker"] += 1
            await asyncio.sleep(self.delay * 1.5)
            i = t.attempts - 1
            ok = t.verdicts[min(i, len(t.verdicts) - 1)]
            reason = t.reasons[i] if i < len(t.reasons) else ("All criteria met." if ok else "Criteria not met.")
            short = t.shorts[i] if i < len(t.shorts) else ("all criteria met" if ok else "criteria not met")
            return AgentResult(text="", structured={"passed": ok, "reason": reason, "short": short},
                               turns=2, cost_usd=self.checker_cost)
        self.calls["worker"] += 1
        self.prompts.append(prompt)
        t.attempts += 1
        root = Path(cwd) if cwd else Path(".")
        for name, inp in t.tools:
            await asyncio.sleep(self.delay)
            if on_tool_use:
                on_tool_use(name, inp)
        if t.outward and can_use_tool:
            name, inp = t.outward
            await can_use_tool(name, inp, None)
        for path, content in t.files:
            await asyncio.sleep(self.delay)
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content + ("" if t.attempts == 1 else f"\n\n<!-- revision {t.attempts} -->"))
            if on_tool_use:
                on_tool_use("Write", {"file_path": str(p), "content": content})
        await asyncio.sleep(self.delay)
        return AgentResult(text=f"Done. Wrote {', '.join(p for p, _ in t.files) or 'nothing'}.", turns=5, cost_usd=t.cost)


class FakeClient:
    """Stands in for ClaudeSDKClient. Runs `script(tools)` on the first query.

    The script is an async generator: `yield "text"` becomes an orchestrator message; it calls
    tools.create_agent / assign_task / finish directly.
    """

    def __init__(self, options, script, state_ref: dict, cost: float = 0.05):
        self.options = options
        self.script = script
        self.state_ref = state_ref
        self.cost = cost
        self.queries = 0
        self.total = 0.0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, prompt):
        self.queries += 1

    async def receive_response(self):
        if self.queries == 1:
            tools = self.state_ref["state"].tools
            async for text in self.script(tools):
                yield AssistantMessage(content=[TextBlock(text=text)], model="fake")
        self.total += self.cost
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=3, session_id="fake", total_cost_usd=self.total)


def fake_client_factory(script, state_ref: dict, cost: float = 0.05):
    return lambda options: FakeClient(options, script, state_ref, cost)


# ---- demo scenario (mirrors the design canvas) ----------------------------------

DEMO_TASK = "Research the top 5 Indonesian e-wallets and write a comparison report as report.md"

_WALLETS = ["gopay", "ovo", "dana", "shopeepay", "linkaja"]


def demo_catalog() -> Catalog:
    entries = [_entry_from_dict(d) for d in BUILTIN_ENTRIES]
    entries.append(Entry(id="gmail", kind="mcp", risk="outward", server={"type": "http", "url": "http://demo"},
                         outward_tools=["send*"], description="Search, read and send email (demo)"))
    return Catalog(entries)


def demo_runner(delay: float = 0.6) -> FakeRunner:
    return FakeRunner({
        "[research]": FakeTask(
            verdicts=[True], shorts=["all 5 files present"],
            reasons=["All 5 files present. Each lists fees, features and 3 to 4 source URLs."],
            tools=[("WebSearch", {"query": "GoPay transfer fees 2026"}), ("WebFetch", {"url": "https://www.gopay.co.id/biaya"})],
            files=[(f"research/{w}.md", f"# {w.title()}\n\n## Fees\n- Transfer: Rp2,500\n\n## Sources\n- https://example.com/{w}")
                   for w in _WALLETS], cost=0.41),
        "[analysis]": FakeTask(
            verdicts=[False, True], shorts=["2 wallets missing fees", "all 5 wallets covered"],
            reasons=["Fee table is missing transfer fees for DANA and LinkAja. ShopeePay is absent from the features matrix.",
                     "Fee table complete for all 5 wallets. Features matrix has 5 columns."],
            tools=[("Read", {"file_path": "research/dana.md"})],
            files=[("analysis/comparison.md", "# Comparison\n\n| Wallet | Transfer |\n|---|---|\n| GoPay | 2,500 |\n| DANA | 2,500 |\n| LinkAja | 1,500 |")],
            cost=0.18),
        "[report-writer]": FakeTask(
            verdicts=[False, False, False],
            shorts=["6 sources, needs 10+", "still 7 sources", "sources in research/ unused"],
            reasons=["Sources list has 6 URLs; needs 10+. Recommendation section is missing.",
                     "Recommendation added. Sources still has 7 URLs.",
                     "Still 7 URLs. The research/ files contain 17 URLs; the report should cite them."],
            files=[("report.md", "# Indonesian e-wallets: a comparison\n\n## Summary\nDANA is cheapest for transfers.")], cost=0.22),
        "[report-editor]": FakeTask(
            verdicts=[True], shorts=["all sections, 17 sources"], reasons=["All sections present. Sources lists 17 URLs."],
            tools=[("Grep", {"pattern": "https://"})],
            outward=("mcp__gmail__send_message", {"to": "me@example.com", "subject": "Your e-wallet report is ready",
                                                   "body": "report.md is in the workspace."}),
            files=[("report.md", "# Indonesian e-wallets: a comparison\n\n## Summary\nDANA is the cheapest for everyday transfers. "
                                 "GoPay has the widest ecosystem. LinkAja wins for sharia-compliant use.\n\n"
                                 "## Fees (IDR)\n\n| Wallet | Top-up | Transfer | Withdrawal |\n|---|---|---|---|\n"
                                 "| GoPay | 1,000 | 2,500 | 5,000 |\n| OVO | 1,000 | 2,500 | n/a |\n| DANA | 0 to 1,000 | 2,500 | 0 |\n"
                                 "| ShopeePay | 0 to 1,000 | 2,500 | 0 |\n| LinkAja | 0 | 1,500 | 0 |\n\n"
                                 "## Recommendation\nFor most people: DANA for transfers, plus the wallet tied to the app you use most.\n\n"
                                 "## Sources\n17 URLs compiled from research/.")], cost=0.24),
    }, delay=delay)


async def demo_script(tools):
    await tools.read_playbook({"id": "research-report"})
    yield "Plan: research each wallet, compare fees and features, then write the report. Research comes first. Hiring three agents."
    for name, role, tl in [("researcher", "Finds fees, features and sources for each wallet", ["web", "files.write"]),
                           ("analyst", "Turns research notes into comparison tables", ["files.read", "files.write"]),
                           ("writer", "Writes the final report from the analysis", ["files.read", "files.write"])]:
        await tools.create_agent({"name": name, "role": role, "system_prompt": f"You are the {name}.", "tools": tl})
    await tools.assign_task({"agent": "researcher", "task_id": "research-1", "title": "Research wallets",
                             "task": "[research] Research GoPay, OVO, DANA, ShopeePay and LinkAja. One file per wallet in research/.",
                             "done_when": "research/ has 5 files, each with fees, features and 3+ source URLs"})
    await tools.assign_task({"agent": "analyst", "task_id": "analysis-1", "title": "Compare fees",
                             "task": "[analysis] Build a fee table and features matrix in analysis/comparison.md.",
                             "done_when": "The fee table covers all 5 wallets; a features matrix with 5 columns"})
    res = await tools.assign_task({"agent": "writer", "task_id": "report-1", "title": "Write the report",
                                   "task": "[report-writer] Write report.md from analysis/ and research/.",
                                   "done_when": "report.md has a summary, 5 wallet sections, the fee table, a recommendation, 10+ sources"})
    if res.get("is_error"):
        yield "The writer can't search the research files. I'm hiring an editor who can, and giving it the report. It will email you when done."
        await tools.create_agent({"name": "editor", "role": "Assembles the report and compiles every source",
                                  "system_prompt": "You are the editor.", "tools": ["files.read", "files.write", "gmail"]})
        await tools.assign_task({"agent": "editor", "task_id": "report-2", "title": "Rewrite the report", "replaces": "report-1",
                                 "task": "[report-editor] Rewrite report.md. Grep research/ for every https:// URL and list them under Sources. Then email the user.",
                                 "done_when": "report.md has a summary, 5 wallet sections, the fee table, a recommendation, 10+ sources"})
    yield "Every task passed verification. Finishing."
    await tools.finish({"result": "Wrote report.md comparing GoPay, OVO, DANA, ShopeePay and LinkAja on fees and features, "
                                  "with a recommendation and 17 sources.\n\nFiles: report.md, analysis/comparison.md, research/ (5 files)."})
