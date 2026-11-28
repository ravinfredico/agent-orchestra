"""Cheap checks: verify parts of a task's done_when without a model call.

The orchestrator attaches `checks` to a task. They run after each worker attempt, before the model
checker. A failing check fails the attempt at once, so no checker usage is spent. With
`checks_only`, passing checks pass the task and the model checker is skipped.

Kinds:
  file_exists  {path}                every path must exist in the workspace
  file_count   {glob, min}           at least `min` files match the glob
  contains     {path, text}          the file contains the text (case-insensitive)
  min_words    {path, min}           the file has at least `min` words
  command      {run}                 the shell command exits 0 (only when shell is on for the run)
"""

import asyncio
import os
from pathlib import Path

KINDS = ["file_exists", "file_count", "contains", "min_words", "command"]
COMMAND_TIMEOUT = 120  # seconds
MAX_FILE = 2_000_000   # bytes read for contains / min_words

SCHEMA = {
    "type": "array",
    "description": "Optional checks run without a model before the checker. A failing check fails the attempt.",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": KINDS},
            "path": {"type": "string", "description": "file_exists, contains, min_words: a workspace file"},
            "glob": {"type": "string", "description": "file_count: e.g. research/*.md"},
            "min": {"type": "integer", "description": "file_count: files; min_words: words"},
            "text": {"type": "string", "description": "contains: text that must appear"},
            "run": {"type": "string", "description": "command: shell command that must exit 0, e.g. pytest -q"},
        },
        "required": ["type"],
    },
}


def label(c: dict) -> str:
    k = c.get("type")
    if k == "file_exists":
        return f"{c.get('path')} exists"
    if k == "file_count":
        return f"{c.get('min', 1)}+ files match {c.get('glob')}"
    if k == "contains":
        return f"{c.get('path')} contains \"{c.get('text')}\""
    if k == "min_words":
        return f"{c.get('path')} has {c.get('min')}+ words"
    if k == "command":
        return f"`{c.get('run')}` exits 0"
    return str(k)


def validate(checks, allow_shell: bool) -> str | None:
    """An error message for bad checks, or None."""
    if not isinstance(checks, list):
        return "checks must be a list"
    for c in checks:
        k = c.get("type") if isinstance(c, dict) else None
        if k not in KINDS:
            return f"Unknown check type {k!r}. Use one of {KINDS}"
        need = {"file_exists": ["path"], "file_count": ["glob"], "contains": ["path", "text"],
                "min_words": ["path", "min"], "command": ["run"]}[k]
        missing = [f for f in need if c.get(f) in (None, "")]
        if missing:
            return f"Check {k} needs {missing}"
        if k == "command" and not allow_shell:
            return ("command checks need shell, which is off for this run. Use file checks, "
                    "or leave it to the checker.")
    return None


def _inside(root: Path, rel: str) -> Path | None:
    p = (root / rel).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return None
    return p


def _read(p: Path) -> str:
    with p.open("rb") as f:
        return f.read(MAX_FILE).decode("utf-8", errors="replace")


async def _one(c: dict, root: Path) -> tuple[bool, str]:
    k = c["type"]
    if k == "command":
        try:
            proc = await asyncio.create_subprocess_shell(
                c["run"], cwd=str(root), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "CI": "1"})
        except OSError as e:
            return False, f"could not start: {e}"
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), COMMAND_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            return False, f"timed out after {COMMAND_TIMEOUT} s"
        except asyncio.CancelledError:
            proc.kill()
            raise
        tail = out.decode("utf-8", errors="replace").strip()[-400:]
        return proc.returncode == 0, f"exit {proc.returncode}" + (f": {tail}" if tail and proc.returncode else "")
    if k == "file_count":
        if ".." in Path(c["glob"]).parts:
            return False, "glob leaves the workspace"
        n = sum(1 for p in root.glob(c["glob"]) if p.is_file())
        need = int(c.get("min") or 1)
        return n >= need, f"{n} found"
    p = _inside(root, c["path"])
    if p is None:
        return False, "path leaves the workspace"
    if not p.is_file():
        return False, "missing"
    if k == "file_exists":
        return True, "found"
    body = _read(p)
    if k == "contains":
        return c["text"].lower() in body.lower(), "found" if c["text"].lower() in body.lower() else "text not found"
    words = len(body.split())
    return words >= int(c["min"]), f"{words} words"


async def run_checks(checks: list[dict], root: Path) -> tuple[bool, list[dict]]:
    """Run every check in order. Returns (all passed, [{check, passed, detail}])."""
    results = []
    for c in checks:
        ok, detail = await _one(c, Path(root))
        results.append({"check": label(c), "passed": ok, "detail": detail})
    return all(r["passed"] for r in results), results


def failure_text(results: list[dict]) -> tuple[str, str]:
    """(reason for the worker, short for the card) from failed results."""
    bad = [r for r in results if not r["passed"]]
    reason = "Checks failed (no model was asked): " + "; ".join(f"{r['check']}: {r['detail']}" for r in bad)
    short = f"{len(bad)} check{'s' if len(bad) > 1 else ''} failed"
    return reason, short
