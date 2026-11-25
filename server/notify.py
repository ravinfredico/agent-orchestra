"""ntfy push notifications (ARCHITECTURE.md section 14). Off unless NTFY_URL is set.

    NTFY_URL=https://ntfy.sh      server (ntfy.sh or your own)
    NTFY_TOPIC=chacha-x7k2…       pick a long random topic: anyone who knows it can read it
    NTFY_TOKEN=                   optional access token for a protected topic
    PUBLIC_URL=http://127.0.0.1:8000   where "open the run" links point (your tunnel URL when hosted)

Sends on: finished (and out of budget), run_failed, approval_requested (high priority).
"""

import json
import os
import threading
import urllib.request
from typing import Callable

PRIORITY = {"min": 1, "low": 2, "default": 3, "high": 4, "max": 5}

KIND_TITLE = {"auth": "Claude login expired", "limit": "Plan usage limit hit"}


def _short(text: str, n: int = 180) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def message_for(event: dict, title: str) -> dict | None:
    """The push for one event, or None if this event doesn't notify."""
    t = event.get("type")
    run = title or "Your run"
    if t == "finished":
        if event.get("give_up"):
            return {"title": f"Out of budget: {run}", "message": _short(event.get("result")) or "Some tasks are unfinished.",
                    "priority": PRIORITY["default"], "tags": ["hourglass"]}
        return {"title": f"Done: {run}", "message": _short(event.get("result")) or "Every task passed the checker.",
                "priority": PRIORITY["default"], "tags": ["white_check_mark"]}
    if t == "run_failed":
        head = KIND_TITLE.get(event.get("kind"), "Run crashed")
        return {"title": f"{head}: {run}", "message": _short(event.get("hint") or event.get("error")) or "Open the run for details.",
                "priority": PRIORITY["high"], "tags": ["warning"]}
    if t == "approval_requested":
        tool = str(event.get("tool", "")).split("__")[-1].replace("_", " ") or "use a tool"
        return {"title": f"Approval needed: {run}", "message": f"{event.get('agent', 'An agent')} wants to {tool}. Open to approve or deny.",
                "priority": PRIORITY["high"], "tags": ["raised_hand"]}
    return None


def _post(url: str, body: dict, token: str | None) -> None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except Exception as e:  # a failed push must never affect a run
        print(f"ntfy: push failed: {e}", flush=True)


class Notifier:
    """Callable passed to RunManager as `notify`. Sends each push on a background thread."""

    def __init__(self, url: str, topic: str, public_url: str = "http://127.0.0.1:8000", token: str | None = None,
                 title_of: Callable[[str], str] = lambda run_id: "", post: Callable[[str, dict, str | None], None] | None = None,
                 background: bool = True):
        self.url = url.rstrip("/")
        self.topic = topic
        self.public_url = public_url.rstrip("/")
        self.token = token or None
        self.title_of = title_of
        self.post = post or _post
        self.background = background

    def __call__(self, event: dict) -> None:
        run_id = event.get("run_id", "")
        msg = message_for(event, self.title_of(run_id))
        if not msg:
            return
        body = {"topic": self.topic, **msg, "click": f"{self.public_url}/runs/{run_id}"}
        if self.background:
            threading.Thread(target=self.post, args=(self.url, body, self.token), daemon=True).start()
        else:
            self.post(self.url, body, self.token)


def from_env(title_of: Callable[[str], str] = lambda run_id: "", env=os.environ) -> Notifier | None:
    url, topic = env.get("NTFY_URL", "").strip(), env.get("NTFY_TOPIC", "").strip()
    if not url or not topic:
        return None
    return Notifier(url, topic, env.get("PUBLIC_URL", "").strip() or "http://127.0.0.1:8000",
                    env.get("NTFY_TOKEN", "").strip() or None, title_of)
