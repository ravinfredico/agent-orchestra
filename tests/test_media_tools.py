"""Video-team tools: the TikTok MCP server (against a fake TikTok API) and the catalog entries."""

import json

import httpx
import pytest

from mcp_servers import tiktok
from orchestra.catalog import load_catalog
from orchestra.config import Config


def fake_tiktok(log: list):
    def handler(req: httpx.Request) -> httpx.Response:
        log.append((req.method, req.url.path, req.headers.get("content-range"), req.content[:200] if req.method == "POST" else len(req.content)))
        assert req.headers["authorization"] == "Bearer tok"
        p = req.url.path
        if p.endswith("/creator_info/query/"):
            return httpx.Response(200, json={"data": {"creator_username": "me", "privacy_level_options": ["SELF_ONLY"]},
                                             "error": {"code": "ok"}})
        if p.endswith("/video/list/"):
            return httpx.Response(200, json={"data": {"videos": [{"id": "1", "view_count": 1800}]}, "error": {"code": "ok"}})
        if p.endswith("/inbox/video/init/") or p.endswith("/publish/video/init/"):
            body = json.loads(req.content)
            if body.get("post_info", {}).get("privacy_level") == "PUBLIC_TO_EVERYONE":
                return httpx.Response(403, json={"error": {"code": "unaudited_client_can_only_post_to_private_accounts",
                                                           "message": "private only"}})
            return httpx.Response(200, json={"data": {"publish_id": "p1", "upload_url": "https://upload.tiktokapis.com/u/1"},
                                             "error": {"code": "ok"}})
        if req.method == "PUT":
            return httpx.Response(201)
        return httpx.Response(404, json={"error": {"code": "not_found"}})
    return httpx.MockTransport(handler)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "tok")
    monkeypatch.delenv("TIKTOK_PRIVACY", raising=False)


def test_reads_creator_and_stats(token):
    log = []
    assert tiktok.creator_info(transport=fake_tiktok(log))["creator_username"] == "me"
    assert tiktok.list_videos(50, transport=fake_tiktok(log))[0]["view_count"] == 1800
    assert b'"max_count": 20' in log[-1][3] or b'"max_count":20' in log[-1][3]      # capped at 20


def test_upload_draft_sends_the_file_in_one_chunk(token, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    log = []
    res = tiktok.upload_draft(str(video), transport=fake_tiktok(log))
    assert res["publish_id"] == "p1" and "inbox" in res["next"]
    assert log[0][1].endswith("/inbox/video/init/")
    assert log[1][0] == "PUT" and log[1][2] == "bytes 0-999/1000" and log[1][3] == 1000


def test_publish_is_private_by_default_and_surfaces_tiktok_errors(token, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 10)
    assert tiktok.publish_video(str(video), "Kos tour", transport=fake_tiktok([]))["privacy_level"] == "SELF_ONLY"
    with pytest.raises(tiktok.TikTokError, match="unaudited"):
        tiktok.publish_video(str(video), "Kos tour", "PUBLIC_TO_EVERYONE", transport=fake_tiktok([]))
    with pytest.raises(tiktok.TikTokError, match="privacy_level"):
        tiktok.publish_video(str(video), "Kos tour", "EVERYONE", transport=fake_tiktok([]))


def test_missing_token_and_file(monkeypatch, tmp_path):
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    with pytest.raises(tiktok.TikTokError, match="TIKTOK_ACCESS_TOKEN"):
        tiktok.creator_info()
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "tok")
    with pytest.raises(tiktok.TikTokError, match="No video"):
        tiktok.upload_draft(str(tmp_path / "missing.mp4"))


def test_catalog_entries_need_their_keys_and_gate_uploads(monkeypatch):
    for v in ("ELEVENLABS_API_KEY", "TIKTOK_ACCESS_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    cat = load_catalog()
    assert cat.by_id["elevenlabs"].unavailable == "set ELEVENLABS_API_KEY in .env"
    assert cat.by_id["tiktok"].unavailable == "set TIKTOK_ACCESS_TOKEN in .env"
    assert "tiktok" not in cat.available_ids(Config())

    monkeypatch.setenv("ELEVENLABS_API_KEY", "el")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "tok")
    cat = load_catalog()
    ts = cat.toolset(["tiktok", "elevenlabs"], Config())
    server = ts.mcp_servers["tiktok"]
    assert server["command"] and server["args"][0].endswith("mcp_servers/tiktok.py")   # ${PYTHON}, ${ORCHESTRA_ROOT}
    assert ts.mcp_servers["elevenlabs"]["env"]["ELEVENLABS_API_KEY"] == "el"
    assert ts.needs_approval_callback
    assert ts.is_outward("mcp__tiktok__publish_video") and ts.is_outward("mcp__tiktok__upload_draft")
    assert not ts.is_outward("mcp__tiktok__list_videos")
    assert ts.is_outward("mcp__elevenlabs__make_outbound_call")
    assert not ts.is_outward("mcp__elevenlabs__text_to_speech")
