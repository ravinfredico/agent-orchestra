"""python -m server [--host 127.0.0.1] [--port 8000] [--runs-dir runs] [--fake]"""

import argparse
import os
from pathlib import Path

import uvicorn

from orchestra.envfile import load_env

from .auth import check_host


def main() -> None:
    p = argparse.ArgumentParser(description="ChaCha PA server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--fake", action="store_true", help="Demo mode: scripted runs, no model calls")
    a = p.parse_args()
    load_env()
    check_host(a.host)
    if a.fake:
        os.environ["ORCHESTRA_FAKE_RUNNER"] = "1"
    from . import notify
    from .app import create_app
    from .runs import RunManager
    mgr = RunManager(a.runs_dir)
    mgr.notify = notify.from_env(mgr.title_of)
    app = create_app(mgr)
    print(f"ChaCha PA on http://{a.host}:{a.port}" + ("  (demo mode, no model calls)" if a.fake else ""))
    if mgr.notify:
        print(f"Push notifications on: ntfy topic '{mgr.notify.topic}' at {mgr.notify.url}")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
