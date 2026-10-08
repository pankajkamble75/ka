# [block plan-02]
"""Access containment and network safety (research-01 R4 step 1, R5).

Access policy (`KA_ACCESS_POLICY`):
    loopback  — only loopback peers, like enterprise-os's `_require_local` (agent_x_mount.py:2661).
    token     — loopback peers always; any other peer must send `Authorization: Bearer <KA_ACCESS_TOKEN>`.
                With no token configured, non-loopback peers are refused (fail closed). This is the default (Q1).
    open      — no check (the pre-plan-02 behaviour).

**This is a containment, not an access policy** (the enterprise-os wording). Behind a reverse proxy every peer is the
proxy, so "loopback" inverts into "everyone": terminate the proxy on a non-loopback interface or use `token`.

URL safety: `is_safe_url` resolves the host and refuses loopback, link-local (including 169.254.169.254), private,
reserved, multicast and unspecified addresses and non-http(s) schemes; `safe_fetch` follows redirects one hop at a time
and re-checks every hop. `KA_URL_ALLOWLIST` names intranet hosts that may be private.
"""
from __future__ import annotations

import hmac
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request

from ka import config

POLICIES = {"loopback", "token", "open"}


def peer_is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else None
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost" or host == "testclient"


def require_access(request: Request) -> None:
    policy = (config.get("KA_ACCESS_POLICY") or "token").lower()
    if policy not in POLICIES:
        policy = "loopback"                      # unknown value → fail closed
    if policy == "open" or peer_is_loopback(request):
        return
    if policy == "loopback":
        raise HTTPException(403, "KA accepts loopback connections only (KA_ACCESS_POLICY=loopback)")
    expected = config.get("KA_ACCESS_TOKEN") or ""
    header = request.headers.get("authorization", "")
    presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not expected or not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "a bearer token is required from this address (KA_ACCESS_TOKEN)",
                            headers={"WWW-Authenticate": "Bearer"})


# ---------------------------------------------------------------- URL safety


def _resolve(host: str) -> list[str]:
    """All A/AAAA addresses for `host`; patched in tests."""
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        return []


def _allowlist() -> set[str]:
    return {h.strip().lower() for h in (config.get("KA_URL_ALLOWLIST") or "").split(",") if h.strip()}


def is_safe_url(url: str) -> tuple[bool, str]:
    try:
        u = urlparse(url)
    except ValueError:
        return False, "unparseable URL"
    if u.scheme not in {"http", "https"}:
        return False, f"scheme {u.scheme or 'none'} is not http(s)"
    host = (u.hostname or "").lower()
    if not host:
        return False, "no host"
    if host in _allowlist():
        return True, "allow-listed host"
    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        resolved = _resolve(host)
        if not resolved:
            return False, f"host {host} does not resolve"
        addrs = [ipaddress.ip_address(a) for a in resolved]
    for a in addrs:
        if a.is_loopback or a.is_link_local or a.is_private or a.is_reserved or a.is_multicast or a.is_unspecified:
            return False, f"{host} resolves to {a} ({_classify(a)})"
    return True, "ok"


def _classify(a: ipaddress._BaseAddress) -> str:
    for name in ("loopback", "link_local", "private", "reserved", "multicast", "unspecified"):
        if getattr(a, f"is_{name}"):
            return name.replace("_", "-")
    return "public"


@dataclass
class Fetched:
    url: str
    content: bytes
    content_type: str
    hops: list[str]


class UnsafeURL(ValueError):
    pass


def safe_fetch(url: str, *, timeout: float = 20.0, max_hops: int = 5, user_agent: str = "enterprise-os-ka/0.1") -> Fetched:
    hops: list[str] = []
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": user_agent}) as client:
        for _ in range(max_hops + 1):
            ok, why = is_safe_url(current)
            if not ok:
                raise UnsafeURL(why)
            hops.append(current)
            r = client.get(current)
            if r.is_redirect and r.headers.get("location"):
                current = str(r.next_request.url) if r.next_request else r.headers["location"]
                continue
            r.raise_for_status()
            return Fetched(current, r.content, r.headers.get("content-type", ""), hops)
    raise UnsafeURL(f"more than {max_hops} redirects")
# [/block plan-02]
