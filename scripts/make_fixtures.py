"""Write real event logs from the scripted demo into web/src/test/fixtures (for the web reducer tests).

    python scripts/make_fixtures.py
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestra import fake
from orchestra.config import Budget, Config
from orchestra.orchestrator import create_run, execute_run
from orchestra.state import read_events

OUT = Path(__file__).resolve().parent.parent / "web" / "src" / "test" / "fixtures"
REPLAY = Path(__file__).resolve().parent.parent / "web" / "src" / "replay"


def scenario(name, config, approve=True):
    tmp = Path(tempfile.mkdtemp())
    s = create_run(fake.DEMO_TASK, config, tmp, run_id=f"20261123-091402-{name}")

    def on(e):
        if e["type"] == "approval_requested":
            asyncio.get_event_loop().call_soon(s.approvals.resolve, e["approval_id"], approve)
    s.add_listener(on)
    asyncio.run(execute_run(s, runner=fake.demo_runner(0), catalog=fake.demo_catalog(), interactive=True,
                            client_factory=fake.fake_client_factory(fake.demo_script, {"state": s})))
    events = read_events(s.run_dir)
    (OUT / f"{name}.json").write_text(json.dumps(events, indent=1))
    if name == "demo":  # the portfolio replay page plays the demo run (web/src/replay)
        (REPLAY / "run.json").write_text(json.dumps(events, indent=1))
    print(name, len(events), "events", s.status)


OUT.mkdir(parents=True, exist_ok=True)
scenario("demo", Config())
scenario("budget", Config(budget=Budget(max_cost_usd=1.0)), approve=False)
