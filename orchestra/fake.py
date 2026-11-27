"""Scripted stand-ins for the model, for offline tests and the server's demo mode.

Never used unless asked for: tests import it directly, and the server only uses it when started
with ORCHESTRA_FAKE_RUNNER=1. No model is called and nothing is billed.

    runner = FakeRunner({"[research]": FakeTask(verdicts=[True], files=[("a.md", "# A")])})
    client_factory = fake_client_factory(script)   # script: async generator using the tools
"""

import asyncio
import re
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
            revised = t.attempts > 1 and path.endswith(".md")   # a comment would break code files
            p.write_text(content + (f"\n\n<!-- revision {t.attempts} -->" if revised else ""))
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


def demo_catalog(connectors: bool = False) -> Catalog:
    entries = [_entry_from_dict(d) for d in BUILTIN_ENTRIES]
    entries.append(Entry(id="gmail", kind="mcp", risk="outward", server={"type": "http", "url": "http://demo"},
                         outward_tools=["send*"], description="Search, read and send email (demo)"))
    entries.append(Entry(id="tiktok", kind="mcp", risk="outward", server={"type": "http", "url": "http://demo"},
                         outward_tools=["post*", "schedule*"], description="Read post stats, schedule posts (demo)"))
    if connectors:  # what your claude.ai connectors look like in the app (demo: nothing is called)
        from .catalog import connector_entries
        from .connectors import Connector
        entries += connector_entries([Connector("claude.ai Figma", "https://mcp.figma.com/mcp", "connected"),
                                      Connector("claude.ai Notion", "https://mcp.notion.com/mcp", "connected"),
                                      Connector("claude.ai Slack", "https://mcp.slack.com/mcp", "needs_auth")])
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
    for name, role, tl, tier, why in [
            ("researcher", "Finds fees, features and sources for each wallet", ["web", "files.write"], "haiku", "search and notes"),
            ("analyst", "Turns research notes into comparison tables", ["files.read", "files.write"], "haiku", "tables from notes"),
            ("writer", "Writes the final report from the analysis", ["files.read", "files.write"], "sonnet", "long-form writing")]:
        await tools.create_agent({"name": name, "role": role, "system_prompt": f"You are the {name}.", "tools": tl,
                                  "tier": tier, "tier_reason": why})
    await tools.assign_task({"agent": "researcher", "task_id": "research-1", "title": "Research wallets",
                             "task": "[research] Research GoPay, OVO, DANA, ShopeePay and LinkAja. One file per wallet in research/.",
                             "done_when": "research/ has 5 files, each with fees, features and 3+ source URLs",
                             "checks": [{"type": "file_count", "glob": "research/*.md", "min": 5}]})
    res = await tools.assign_tasks({"tasks": [
        {"agent": "analyst", "task_id": "analysis-1", "title": "Compare fees", "owns": ["analysis/"],
         "task": "[analysis] Build a fee table and features matrix in analysis/comparison.md.",
         "done_when": "The fee table covers all 5 wallets; a features matrix with 5 columns"},
        {"agent": "writer", "task_id": "report-1", "title": "Write the report", "depends_on": ["analysis-1"],
         "owns": ["report.md"], "task": "[report-writer] Write report.md from analysis/ and research/.",
         "done_when": "report.md has a summary, 5 wallet sections, the fee table, a recommendation, 10+ sources"}]})
    if res.get("is_error"):
        yield "The writer can't search the research files. I'm hiring an editor who can, and giving it the report. It will email you when done."
        await tools.create_agent({"name": "editor", "role": "Assembles the report and compiles every source",
                                  "system_prompt": "You are the editor.", "tools": ["files.read", "files.write", "gmail"],
                                  "tier": "sonnet", "tier_reason": "editing and sources"})
        await tools.assign_task({"agent": "editor", "task_id": "report-2", "title": "Rewrite the report", "replaces": "report-1",
                                 "task": "[report-editor] Rewrite report.md. Grep research/ for every https:// URL and list them under Sources. Then email the user.",
                                 "done_when": "report.md has a summary, 5 wallet sections, the fee table, a recommendation, 10+ sources"})
    yield "Every task passed verification. Finishing."
    async for line in _finish(tools, "Wrote report.md comparing GoPay, OVO, DANA, ShopeePay and LinkAja on fees and features, "
                                     "with a recommendation and 17 sources.\n\nFiles: report.md, analysis/comparison.md, research/ (5 files)."):
        yield line


# ---- build scenario: a small app with tests (picked for build-style tasks) -----------
# The code is real: the finished workspace passes its own pytest suite. The first version has a
# genuine bug (`done 0` ticks the last todo, `done 3` crashes) that the tester's suite catches.

DEMO_BUILD_TASK = "Build a Python CLI todo app with pytest tests that all pass"

_FILES = Path(__file__).parent / "demo_files"
_BUILD_KEYWORDS = re.compile(r"\b(build|app|cli|code|script|program|tests?|pytest|api|function|game)\b", re.I)


def _todo_sources() -> tuple[str, str, str]:
    fixed = (_FILES / "todo.py.txt").read_text()
    tests = (_FILES / "test_todo.py.txt").read_text()
    check = """    if not 1 <= n <= len(items):
        raise ValueError(f"there is no todo number {n}")
"""
    assert check in fixed
    return fixed.replace(check, ""), fixed, tests


_README = """# todo

A tiny todo list for the terminal. Todos are saved in `todos.json`.

```
python todo.py add "buy milk"
python todo.py list
python todo.py done 1
python todo.py remove 1
```

Run the tests with `pytest -q`.
"""


def demo_build_runner(delay: float = 0.6) -> FakeRunner:
    buggy, fixed, tests = _todo_sources()
    return FakeRunner({
        "[dev-core]": FakeTask(
            verdicts=[False, True], shorts=["list is empty after add", "add and list work"],
            reasons=["Ran `python todo.py add \"buy milk\"` then `python todo.py list`: it printed \"Nothing to do.\" "
                     "Todos are not saved to todos.json.",
                     "`add` then `list` prints \"1. [ ] buy milk\". `done 1` ticks it. Todos persist in todos.json."],
            tools=[("Bash", {"command": 'python todo.py add "buy milk" && python todo.py list'})],
            files=[("todo.py", buggy)], cost=0.31),
        "[tests]": FakeTask(
            verdicts=[False, False, False],
            shorts=["4 tests fail: bug in todo.py", "same 4 failures", "tests are right; todo.py is wrong"],
            reasons=["Ran `pytest -q`: 4 failed, 7 passed. `done 0` ticks the last todo instead of failing, and "
                     "`done 3` on a 2-item list raises IndexError. The bug is in todo.py, not the tests.",
                     "Same 4 failures. The tester can't fix todo.py, and changing the tests to match the bug is not allowed.",
                     "Still 4 failures. The tests are correct: todo.py must reject numbers that are not on the list."],
            tools=[("Read", {"file_path": "todo.py"}), ("Bash", {"command": "pytest -q"})],
            files=[("test_todo.py", tests)], cost=0.27),
        "[dev-fix]": FakeTask(
            verdicts=[True], shorts=["11 tests pass"],
            reasons=["Ran `pytest -q`: 11 passed. `python todo.py done 9` prints \"error: there is no todo number 9\" and exits 1. "
                     "README.md explains every command."],
            tools=[("Read", {"file_path": "test_todo.py"}), ("Bash", {"command": "pytest -q"})],
            files=[("todo.py", fixed), ("README.md", _README)], cost=0.24),
    }, delay=delay)


async def demo_build_script(tools):
    await tools.read_playbook({"id": "build-with-tests"})
    shell = tools.s.config.allow_bash
    yield ("Plan: a developer writes todo.py, then a tester writes pytest tests for every command, including bad input. "
           "The checker runs the code and the tests itself. Hiring two agents.")
    if not shell:
        yield "Shell is off, so nobody can run the code or the tests. Turn on shell commands for a checked build."
    extra = ["shell"] if shell else []
    await tools.create_agent({"name": "developer", "role": "Writes and fixes the app code", "system_prompt": "You are the developer.",
                              "tools": ["files.read", "files.write", *extra], "tier": "sonnet", "tier_reason": "writes code"})
    await tools.create_agent({"name": "tester", "role": "Writes pytest tests and runs them", "system_prompt": "You are the tester.",
                              "tools": ["files.read", "files.write", *extra], "tier": "haiku", "tier_reason": "tests from a spec"})
    await tools.assign_task({"agent": "developer", "task_id": "app-1", "title": "Write the todo app",
                             "task": "[dev-core] Write todo.py: add, list, done N, remove N. Save todos in todos.json.",
                             "done_when": '`python todo.py add "buy milk"` then `python todo.py list` prints "1. [ ] buy milk"'})
    res = await tools.assign_task({"agent": "tester", "task_id": "tests-1", "title": "Write the tests",
                                   "task": "[tests] Write test_todo.py covering every command and bad input. Run pytest -q.",
                                   "done_when": "`pytest -q` exits 0 with at least 8 tests, including bad numbers and empty text"})
    if res.get("is_error"):
        yield ("The tests found a real bug: done and remove accept numbers that aren't on the list. That's in todo.py, "
               "so the fix goes to the developer, not the tester.")
        await tools.assign_task({"agent": "developer", "task_id": "app-fix", "title": "Fix bad numbers", "replaces": "tests-1",
                                 "task": "[dev-fix] Make done and remove reject numbers not on the list, with an error and exit 1. "
                                         "Don't change test_todo.py. Add a README.md.",
                                 "done_when": "`pytest -q` exits 0 with at least 8 tests; README.md lists every command"})
    yield "Every task passed verification. Finishing."
    async for line in _finish(tools, "Built a todo CLI in todo.py (add, list, done, remove, saved in todos.json) with 11 passing "
                                     "pytest tests. The tests caught a bug with bad todo numbers, which the developer fixed.\n\n"
                                     "Files: todo.py, test_todo.py, README.md. Try it: python todo.py add \"buy milk\""):
        yield line


async def _finish(tools, result: str):
    """finish, and if it was refused because you sent a message mid-run, acknowledge it and finish again."""
    res = await tools.finish({"result": result})
    if res.get("is_error") and "Message from the user" in res["content"][0]["text"]:
        yield "Got your message. Noted for this result and the team's next run."
        await tools.finish({"result": result})


# ---- TikTok team scenario (picked for TikTok or video tasks and teams) ------------------

TIKTOK_MEMBERS = [
    {"name": "trendscout", "role": "Finds trends, sounds and hooks", "tools": ["web", "files.write"], "tier": "haiku"},
    {"name": "analyst", "role": "Reads last week's post stats", "tools": ["tiktok", "files.write"], "tier": "haiku"},
    {"name": "scriptwriter", "role": "Writes hooks, scripts and captions", "tools": ["files.read", "files.write"], "tier": "sonnet"},
    {"name": "editor", "role": "Renders vertical videos with Remotion", "tools": ["files.read", "files.write"], "tier": "sonnet"},
    {"name": "poster", "role": "Schedules posts, always with your approval", "tools": ["files.read", "tiktok"], "tier": "haiku"},
]
_IDEAS = [("01-kos-tour", "A Rp1.5 million kos room tour in Depok"), ("02-krl-rush", "Surviving the 7am KRL rush"),
          ("03-thesis-cafe", "Ranking Jakarta cafes for thesis writing")]


def demo_tiktok_runner(delay: float = 0.6) -> FakeRunner:
    return FakeRunner({
        "[tt-trends]": FakeTask(
            shorts=["8 trends, 3 picked"], reasons=["trends.md lists 8 trends with sounds and why each fits; 3 are picked."],
            tools=[("WebSearch", {"query": "TikTok trends Indonesia student life this week"}),
                   ("WebFetch", {"url": "https://ads.tiktok.com/business/creativecenter/trends"})],
            files=[("trends.md", "# Trends this week\n\n1. Room tours on a budget (sound: 'Lagi Tren')\n2. Commute POV\n3. Cafe rankings\n"
                                 "\nPicked: room tour, commute POV, cafe ranking.")], cost=0.06),
        "[tt-stats]": FakeTask(
            shorts=["5 posts reviewed"], reasons=["stats.md covers last week's 5 posts with views, likes, watch time and 3 lessons."],
            tools=[("mcp__tiktok__get_post_stats", {"days": 7})],
            files=[("stats.md", "# Last week\n\n| Post | Views | Watch time |\n|---|---|---|\n| Cooking hack | 2.1k | 31% |\n"
                                "| Campus tour | 18.4k | 64% |\n\nLessons: hooks under 2 s, faces in frame 1, skip cooking.")], cost=0.05),
        "[tt-scripts]": FakeTask(
            verdicts=[False, True], shorts=["2 hooks over 3 seconds", "3 scripts, hooks under 2 s"],
            reasons=["Scripts 1 and 3 open with a 5 second intro; the stats say hooks must land in 2 seconds.",
                     "All 3 scripts open with a hook under 2 seconds, have captions and 5 hashtags each."],
            tools=[("Read", {"file_path": "trends.md"}), ("Read", {"file_path": "stats.md"})],
            files=[(f"scripts/{slug}.md", f"# {title}\n\nHook (0-2 s): ...\n\nCaption: ...\n\n#anakkos #jakarta #mahasiswa #fyp #studentlife")
                   for slug, title in _IDEAS], cost=0.2),
        "[tt-render]": FakeTask(
            shorts=["3 storyboards, 1080x1920"], reasons=["3 storyboards at 1080x1920 with voiceover lines, each under 30 s."],
            tools=[("Read", {"file_path": "scripts/01-kos-tour.md"})],
            files=[(f"videos/{slug}.storyboard.md", f"# {title}\n\nFormat: 1080x1920, 24 s, voiceover\n\n(demo: no real render)")
                   for slug, title in _IDEAS], cost=0.22),
        "[tt-post]": FakeTask(
            shorts=["3 posts scheduled"], reasons=["3 posts scheduled for Mon, Wed and Fri at 18:00 WIB."],
            outward=("mcp__tiktok__schedule_posts", {"posts": [s for s, _ in _IDEAS], "times": ["Mon 18:00", "Wed 18:00", "Fri 18:00"]}),
            files=[("schedule.md", "# Scheduled\n\n- Mon 18:00 kos tour\n- Wed 18:00 KRL rush\n- Fri 18:00 thesis cafes")], cost=0.04),
    }, delay=delay)


async def demo_tiktok_script(tools):
    await tools.read_playbook({"id": "short-video"})
    yield ("Plan: the trend scout and the analyst work at the same time, then the script writer drafts 3 videos, "
           "the editor renders them, and the poster schedules them once you approve.")
    for m in TIKTOK_MEMBERS:
        if m["name"] not in tools.s.agents:
            await tools.create_agent({**m, "system_prompt": f"You are the team's {m['name']}.", "tier_reason": "team member"})
    await tools.assign_tasks({"tasks": [
        {"agent": "trendscout", "task_id": "trends-1", "title": "Find this week's trends", "owns": ["trends.md"],
         "task": "[tt-trends] Find 8 student-life trends in Indonesia this week with sounds. Pick the 3 best. Save trends.md.",
         "done_when": "trends.md lists 8 trends with a sound each and marks 3 picks",
         "checks": [{"type": "file_exists", "path": "trends.md"}]},
        {"agent": "analyst", "task_id": "stats-1", "title": "Review last week", "owns": ["stats.md"],
         "task": "[tt-stats] Read last week's post stats. Save stats.md with a table and 3 lessons.",
         "done_when": "stats.md has every post from the last 7 days and 3 lessons",
         "checks": [{"type": "contains", "path": "stats.md", "text": "Lessons"}]},
    ]})
    msgs = tools.s.take_messages()
    if msgs:
        yield f"Got it: \"{msgs[-1]}\". The stats agree (cooking had the lowest watch time), so none of the 3 ideas are cooking."
    await tools.assign_task({"agent": "scriptwriter", "task_id": "scripts-1", "title": "Write 3 scripts",
                             "task": "[tt-scripts] Write 3 scripts from the picked trends, using the lessons in stats.md. One file each in scripts/.",
                             "done_when": "3 scripts, each with a hook under 2 seconds, a caption and 5 hashtags",
                             "checks": [{"type": "file_count", "glob": "scripts/*.md", "min": 3}]})
    await tools.assign_task({"agent": "editor", "task_id": "render-1", "title": "Render 3 videos",
                             "task": "[tt-render] Render the 3 scripts as 1080x1920 videos with a voiceover, under 30 s each.",
                             "done_when": "3 vertical videos, each under 30 s, in videos/"})
    yield "Videos are ready. The poster will schedule them for Mon, Wed and Fri at 18:00, after you approve."
    await tools.assign_task({"agent": "poster", "task_id": "post-1", "title": "Schedule 3 posts",
                             "task": "[tt-post] Schedule the 3 videos on TikTok for Mon, Wed and Fri at 18:00 WIB.",
                             "done_when": "3 posts scheduled at the agreed times"})
    async for line in _finish(tools, "3 TikToks ready and scheduled for Mon, Wed and Fri at 18:00: a kos room tour, the KRL rush, "
                                     "and a thesis-cafe ranking. No cooking. Hooks are under 2 seconds, as last week's stats suggest.\n\n"
                                     "Files: trends.md, stats.md, scripts/ (3), videos/ (3), schedule.md."):
        yield line


_TIKTOK_KEYWORDS = re.compile(r"tiktok|video|reel|konten", re.I)


def pick_demo(task: str, team: dict | None = None):
    """Demo mode: TikTok for video tasks or teams, build for build-style tasks, otherwise research."""
    about = f"{task or ''} {(team or {}).get('name', '')} {(team or {}).get('goal', '')}"
    if _TIKTOK_KEYWORDS.search(about):
        return demo_tiktok_runner, demo_tiktok_script
    if _BUILD_KEYWORDS.search(task or ""):
        return demo_build_runner, demo_build_script
    return demo_runner, demo_script
