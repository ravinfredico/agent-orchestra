"""PWA install (IMPLEMENTATION.md 5.4): the manifest is complete and every icon matches its size."""

import json
import struct
from pathlib import Path

PUBLIC = Path(__file__).parent.parent / "web" / "public"


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", head[16:24])


def test_manifest_is_installable():
    m = json.loads((PUBLIC / "manifest.webmanifest").read_text())
    assert m["name"] and m["short_name"] and m["start_url"] == "/" and m["display"] == "standalone"
    sizes = set()
    for icon in m["icons"]:
        f = PUBLIC / icon["src"].lstrip("/")
        assert f.is_file(), icon["src"]
        w, h = png_size(f)
        assert f"{w}x{h}" == icon["sizes"], icon["src"]
        sizes.add((icon["sizes"], icon.get("purpose", "any")))
    assert ("192x192", "any") in sizes and ("512x512", "any") in sizes and ("512x512", "maskable") in sizes


def test_index_links_manifest_and_apple_icon():
    html = (PUBLIC.parent / "index.html").read_text()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'rel="apple-touch-icon" href="/icons/apple-touch-icon.png"' in html
    assert png_size(PUBLIC / "icons" / "apple-touch-icon.png") == (180, 180)
