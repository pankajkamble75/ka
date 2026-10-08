"""Images tab — numbered screenshots for conversations (ka/images.py). Not knowledge; never governed."""
from __future__ import annotations

import base64
import io

import pytest
from fastapi.testclient import TestClient

from ka import images
from ka.api import PREFIX, create_app, set_ka


def _png(w=4, h=3) -> bytes:
    import struct
    import zlib
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_P1_numbers_are_sequential_and_never_reused(tmp_path):
    a = images.save(tmp_path, data_b64=base64.b64encode(_png()).decode(), name="a.png")
    b = images.save(tmp_path, data_b64=base64.b64encode(_png(5, 5)).decode(), caption="second")
    assert (a["number"], b["number"]) == (1, 2) and a["width"] == 4 and b["caption"] == "second"
    assert a["path"].endswith("images/0001.png")
    images.delete(tmp_path, 2)
    c = images.save(tmp_path, data_b64=base64.b64encode(_png()).decode())
    assert c["number"] == 3 and [r["number"] for r in images.list_images(tmp_path)] == [3, 1]
    data, mime = images.read(tmp_path, 1)
    assert mime == "image/png" and data == _png()
    with pytest.raises(ValueError):
        images.read(tmp_path, 2)


def test_N1_non_images_and_oversize_are_refused(tmp_path):
    with pytest.raises(ValueError):
        images.save(tmp_path, data_b64=base64.b64encode(b"hello").decode())
    with pytest.raises(ValueError):
        images.save(tmp_path, data_b64="not base64!!")
    with pytest.raises(ValueError):
        images.save(tmp_path, data_b64="A" * ((images.MAX_BYTES + 2) // 3 * 4 + 8))


def test_P2_api_round_trip(ka):
    client = TestClient(create_app(ka))
    try:
        r = client.post(f"{PREFIX}/images", json={"data": base64.b64encode(_png()).decode(), "name": "shot.png", "caption": "menu"})
        assert r.status_code == 200 and r.json()["image"]["number"] == 1
        assert client.get(f"{PREFIX}/images/1").headers["content-type"] == "image/png"
        assert client.post(f"{PREFIX}/images/1/caption", json={"caption": "menu v2"}).json()["image"]["caption"] == "menu v2"
        assert client.get(f"{PREFIX}/images").json()["images"][0]["name"] == "shot.png"
        assert client.post(f"{PREFIX}/images/9/delete").status_code == 404
        assert client.post(f"{PREFIX}/images", json={"data": base64.b64encode(b"nope").decode()}).status_code == 400
    finally:
        set_ka(None)
