"""Playbooks: proven steps per kind of task, picked by the orchestrator before it plans.

One markdown file per playbook in orchestra/playbooks/, with front matter `id`, `title`, `when`.
The orchestrator sees the summaries and reads the full playbook with the `read_playbook` tool.
Agents are still invented freely; a playbook only gives steps, done-when templates and pitfalls.
"""

from dataclasses import dataclass
from pathlib import Path

PLAYBOOKS_DIR = Path(__file__).resolve().parent / "playbooks"
REQUIRED = ("id", "title", "when")


@dataclass(frozen=True)
class Playbook:
    id: str
    title: str
    when: str
    body: str


def _parse(path: Path) -> Playbook:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing front matter")
    head, body = text[4:].split("\n---\n", 1)
    meta = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise ValueError(f"{path.name}: front matter needs {missing}")
    return Playbook(meta["id"], meta["title"], meta["when"], body.strip())


def load_playbooks(folder: Path = PLAYBOOKS_DIR) -> dict[str, Playbook]:
    books = [_parse(p) for p in sorted(Path(folder).glob("*.md"))]
    return {b.id: b for b in books}


def summary_lines(books: dict[str, Playbook]) -> str:
    return "\n".join(f"- {b.id}: {b.title}. {b.when}" for b in books.values())
