"""python -m server [--host 127.0.0.1] [--port 8000] [--runs-dir runs] [--fake]"""

import argparse
import os
from pathlib import Path

import uvicorn

from .auth import check_host


def main() -> None:
    p = argparse.ArgumentParser(description="ChaCha PA server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--fake", action="store_true", help="Demo mode: scripted runs, no model calls")
    a = p.parse_args()
    check_host(a.host)
    if a.fake:
        os.environ["ORCHESTRA_FAKE_RUNNER"] = "1"
    from .app import create_app
    from .runs import RunManager
    app = create_app(RunManager(a.runs_dir))
    print(f"ChaCha PA on http://{a.host}:{a.port}" + ("  (demo mode, no model calls)" if a.fake else ""))
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
