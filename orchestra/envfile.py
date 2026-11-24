"""Load KEY=value lines from .env into os.environ. Variables already set in the shell win."""

import os
from pathlib import Path


def load_env(path: Path = Path(".env"), env=os.environ) -> list[str]:
    """Returns the names it set. Ignores blank lines, comments and empty values."""
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key or not value or key in env:
            continue
        if key == "ANTHROPIC_API_KEY":   # plan mode depends on this staying unset unless you export it yourself
            continue
        env[key] = value
        loaded.append(key)
    return loaded
