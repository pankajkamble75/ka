"""Numbered images for conversations (same contract as sdlc-orchestrator's images.py).

Paste, drop or choose a screenshot on the Images tab; it is stored as <storage>/images/NNNN.<ext> with a
sequential number. The console shows "image #N", the server path and a link (/console/#/images?image=N),
so the person can say "look at image #3" and whoever helps (a person or the coding assistant on this
server) opens the file by its path. Deleted numbers are never reused, so earlier references stay unambiguous.
Images are not knowledge: they never enter governance unless someone ingests one as a source separately.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import struct
import threading
import time
from pathlib import Path
from typing import Any

MAX_BYTES = 10 * 1024 * 1024
TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
_LOCK = threading.Lock()


def folder(storage_root: Path) -> Path:
    return Path(storage_root) / "images"


def _kind(data: bytes) -> tuple[str, tuple[int, int] | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33 and data[12:16] == b"IHDR":
        return "png", struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", None
    if len(data) >= 20 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", None
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return "gif", struct.unpack("<HH", data[6:10])
    raise ValueError("Only PNG, JPEG, WebP and GIF images are supported.")


def _index(root: Path) -> list[dict[str, Any]]:
    try:
        return json.loads((folder(root) / "index.json").read_text())
    except (OSError, ValueError):
        return []


def _write_index(root: Path, rows: list[dict[str, Any]]) -> None:
    path = folder(root) / "index.json"
    tmp = path.with_name("index.json.tmp")
    tmp.write_text(json.dumps(rows, indent=1))
    tmp.replace(path)


def save(root: Path, *, data_b64: str, name: str = "pasted image", caption: str = "") -> dict[str, Any]:
    if not isinstance(data_b64, str) or len(data_b64) > (MAX_BYTES + 2) // 3 * 4:
        raise ValueError("Choose an image up to 10 MB.")
    if len(caption) > 2000 or len(name) > 255:
        raise ValueError("Caption up to 2000 and name up to 255 characters.")
    try:
        data = base64.b64decode(data_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid image encoding.") from exc
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Choose an image up to 10 MB.")
    ext, size = _kind(data)
    dir_ = folder(root)
    dir_.mkdir(mode=0o700, parents=True, exist_ok=True)
    with _LOCK:
        rows = _index(root)
        number = max([r["number"] for r in rows] or [0]) + 1
        path = dir_ / f"{number:04d}.{ext}"
        path.write_bytes(data)
        path.chmod(0o600)
        row = dict(number=number, path=str(path), name=name.strip()[:255] or "pasted image", caption=caption.strip(), mime=TYPES[ext],
                   bytes=len(data), width=size[0] if size else None, height=size[1] if size else None,
                   sha256=hashlib.sha256(data).hexdigest(), created_at=time.time())
        _write_index(root, rows + [row])
    return row


def list_images(root: Path) -> list[dict[str, Any]]:
    return sorted((r for r in _index(root) if not r.get("deleted")), key=lambda r: -r["number"])


def read(root: Path, number: int) -> tuple[bytes, str]:
    row = next((r for r in _index(root) if r["number"] == number and not r.get("deleted")), None)
    if row is None:
        raise ValueError(f"Image #{number} does not exist.")
    path = Path(row["path"])
    if path.is_symlink() or not path.is_file() or path.parent != folder(root):
        raise ValueError(f"Image #{number} is missing.")
    return path.read_bytes(), row["mime"]


def update(root: Path, number: int, caption: str) -> dict[str, Any]:
    if len(caption) > 2000:
        raise ValueError("Caption up to 2000 characters.")
    with _LOCK:
        rows = _index(root)
        row = next((r for r in rows if r["number"] == number and not r.get("deleted")), None)
        if row is None:
            raise ValueError(f"Image #{number} does not exist.")
        row["caption"] = caption.strip()
        _write_index(root, rows)
        return row


def delete(root: Path, number: int) -> dict[str, Any]:
    """Remove an image; its number is never reused."""
    with _LOCK:
        rows = _index(root)
        row = next((r for r in rows if r["number"] == number and not r.get("deleted")), None)
        if row is None:
            raise ValueError(f"Image #{number} does not exist.")
        Path(row["path"]).unlink(missing_ok=True)
        _write_index(root, [r for r in rows if r["number"] != number] + [dict(number=number, deleted=True, created_at=row["created_at"], deleted_at=time.time())])
        return dict(number=number, deleted=True)
