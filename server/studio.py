"""Video studio (M10): the videos a team made, ready for you to post by hand.

A team saves each video as a file pair in a run's workspace:
  videos/<name>.mp4   the rendered video (optional: without it the item is "script only")
  videos/<name>.md    "# Title", a "Caption:" line, and hashtags (#word)

Nothing is uploaded anywhere. You copy the caption, download the video, post it yourself and mark it
posted. Posted marks live in teams/<id>/studio.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_TAG = re.compile(r"(?<![\w#])#[\w]+", re.U)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
VIDEO_EXT = ".mp4"


def parse_card(text: str, name: str) -> dict:
    """Title, caption and hashtags from a video's .md file."""
    title, caption, tags = "", "", []
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for ln in lines:
        if not title and ln.startswith("# "):
            title = ln[2:].strip()
        m = re.match(r"(?i)^\**caption\**\s*[:：]\s*(.+)$", ln)
        if m and not caption:
            caption = m.group(1).strip()
    if not caption:  # first plain paragraph line that isn't a heading or only hashtags
        caption = next((ln for ln in lines if ln and not ln.startswith("#") and not ln.lower().startswith(("hook", "voiceover", "format"))), "")
    for ln in lines:
        tags += _TAG.findall(ln)
    caption = " ".join(_TAG.sub("", caption).split())   # hashtags are listed on their own
    return {"title": title or name.replace("-", " ").replace("_", " ").strip(), "caption": caption[:2200],
            "hashtags": list(dict.fromkeys(tags))[:30]}


def items(run_dirs: list[Path], workspace_of, posted: dict) -> list[dict]:
    """Every video in the team's runs, newest first. workspace_of(run_id) -> Path."""
    out = []
    for d in run_dirs:
        run_id = Path(d).name
        vids = Path(workspace_of(run_id)) / "videos"
        if not vids.is_dir():
            continue
        names = sorted({p.stem for p in vids.iterdir() if p.suffix.lower() in (VIDEO_EXT, ".md") and _NAME.fullmatch(p.stem)})
        for name in names:
            md, mp4 = vids / f"{name}.md", vids / f"{name}{VIDEO_EXT}"
            card = parse_card(md.read_text(errors="replace") if md.is_file() else "", name)
            ref = mp4 if mp4.is_file() else md
            item_id = f"{run_id}/{name}"
            out.append({"id": item_id, "run_id": run_id, "name": name, **card,
                        "video": f"videos/{name}{VIDEO_EXT}" if mp4.is_file() else None,
                        "script": f"videos/{name}.md" if md.is_file() else None,
                        "created": round(ref.stat().st_mtime, 2), "posted_at": posted.get(item_id)})
    out.sort(key=lambda i: i["created"], reverse=True)
    return out


def load_posted(team_dir: Path) -> dict:
    p = Path(team_dir) / "studio.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def set_posted(team_dir: Path, item_id: str, when: float | None) -> dict:
    marks = load_posted(team_dir)
    if when is None:
        marks.pop(item_id, None)
    else:
        marks[item_id] = round(when, 2)
    (Path(team_dir) / "studio.json").write_text(json.dumps(marks, indent=1))
    return marks
