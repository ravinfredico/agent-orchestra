"""A small MCP server for TikTok (catalog id `tiktok`), on TikTok's official v2 APIs.

    TIKTOK_ACCESS_TOKEN=... python mcp_servers/tiktok.py      # stdio; the catalog starts it for agents

Tools:
  creator_info     who is signed in, allowed privacy levels, max video length     (read)
  list_videos      recent posts with views, likes, comments, shares (Display API) (read)
  upload_draft     send a video to your TikTok inbox as a draft; you finish it    (outward: asks you)
  publish_video    post directly, private by default (TIKTOK_PRIVACY)            (outward: asks you)
  post_status      check a draft or post by publish_id                           (read)

Needs a TikTok developer app with Login Kit and the Content Posting API, and a user access token
with the scopes for what you use: user.info.basic, video.list, video.upload, video.publish.
Until TikTok audits the app, posts can only be private (SELF_ONLY) and the account must be private.
Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

API = "https://open.tiktokapis.com/v2"
MAX_SINGLE_UPLOAD = 64 * 1024 * 1024    # TikTok accepts one chunk up to 64 MB
VIDEO_FIELDS = "id,title,create_time,duration,view_count,like_count,comment_count,share_count,share_url"
PRIVACY = {"SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"}


class TikTokError(Exception):
    pass


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        raise TikTokError("TIKTOK_ACCESS_TOKEN is not set. Add it to .env (see docs/ARCHITECTURE.md, TikTok).")
    return httpx.Client(headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                        timeout=60, transport=transport)


def _call(c: httpx.Client, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    r = c.post(f"{API}{path}", json=body or {}, params=params)
    try:
        data = r.json()
    except ValueError:
        raise TikTokError(f"TikTok answered {r.status_code} without JSON")
    err = data.get("error") or {}
    if r.status_code >= 400 or (err.get("code") not in (None, "", "ok")):
        raise TikTokError(f"TikTok error {err.get('code') or r.status_code}: {err.get('message') or r.text[:200]}")
    return data.get("data") or {}


def _video(path: str) -> tuple[Path, int]:
    p = Path(path)
    if not p.is_file():
        raise TikTokError(f"No video file at {path}")
    size = p.stat().st_size
    if size > MAX_SINGLE_UPLOAD:
        raise TikTokError(f"{path} is {size // (1024 * 1024)} MB; this server uploads up to 64 MB. Render a smaller file.")
    return p, size


def _upload(c: httpx.Client, upload_url: str, p: Path, size: int) -> None:
    r = c.put(upload_url, content=p.read_bytes(),
              headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if r.status_code >= 400:
        raise TikTokError(f"Upload failed with {r.status_code}")


def _source(size: int) -> dict:
    return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}


# ---- tool bodies (plain functions, tested offline with a mock transport) ---------------------

def creator_info(transport=None) -> dict:
    with _client(transport) as c:
        return _call(c, "/post/publish/creator_info/query/")


def list_videos(max_count: int = 10, transport=None) -> list[dict]:
    with _client(transport) as c:
        data = _call(c, "/video/list/", {"max_count": max(1, min(int(max_count), 20))}, {"fields": VIDEO_FIELDS})
        return data.get("videos", [])


def upload_draft(video_path: str, transport=None) -> dict:
    p, size = _video(video_path)
    with _client(transport) as c:
        data = _call(c, "/post/publish/inbox/video/init/", {"source_info": _source(size)})
        _upload(c, data["upload_url"], p, size)
        return {"publish_id": data.get("publish_id"), "next": "Open TikTok: the draft is in your inbox to edit and post."}


def publish_video(video_path: str, title: str, privacy_level: str = "", transport=None) -> dict:
    privacy = privacy_level or os.environ.get("TIKTOK_PRIVACY", "SELF_ONLY")
    if privacy not in PRIVACY:
        raise TikTokError(f"privacy_level must be one of {sorted(PRIVACY)}")
    p, size = _video(video_path)
    with _client(transport) as c:
        data = _call(c, "/post/publish/video/init/", {
            "post_info": {"title": title[:2200], "privacy_level": privacy},
            "source_info": _source(size),
        })
        _upload(c, data["upload_url"], p, size)
        return {"publish_id": data.get("publish_id"), "privacy_level": privacy}


def post_status(publish_id: str, transport=None) -> dict:
    with _client(transport) as c:
        return _call(c, "/post/publish/status/fetch/", {"publish_id": publish_id})


def main() -> None:
    try:  # mcp 2.x renamed FastMCP to MCPServer; same decorator API
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server

    app = Server("tiktok")

    def safe(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except TikTokError as e:
            return {"error": str(e)}

    @app.tool(name="creator_info")
    def creator_info_tool() -> dict:
        """Who is signed in, which privacy levels are allowed, and the max video length."""
        return safe(creator_info)

    @app.tool(name="list_videos")
    def list_videos_tool(max_count: int = 10) -> list | dict:
        """Recent posts with views, likes, comments and shares (newest first, up to 20)."""
        return safe(list_videos, max_count)

    @app.tool(name="upload_draft")
    def upload_draft_tool(video_path: str) -> dict:
        """Send an MP4 from the workspace to the user's TikTok inbox as a draft. Needs the user's approval."""
        return safe(upload_draft, video_path)

    @app.tool(name="publish_video")
    def publish_video_tool(video_path: str, title: str, privacy_level: str = "") -> dict:
        """Post an MP4 directly. Private (SELF_ONLY) unless TIKTOK_PRIVACY or privacy_level says otherwise. Needs approval."""
        return safe(publish_video, video_path, title, privacy_level)

    @app.tool(name="post_status")
    def post_status_tool(publish_id: str) -> dict:
        """Check a draft or post by its publish_id."""
        return safe(post_status, publish_id)

    app.run()


if __name__ == "__main__":
    main()
