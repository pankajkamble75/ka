# [block plan-07]
"""Discovery before fetching (research-01 R9): query → search results → selection → the Internet agent fetches.

The search provider is a SEAM (Q5): `SearchProvider` is a protocol; `NullSearchProvider` answers nothing and says so,
`FixtureSearchProvider` serves a JSON file. Selection honours an allow-list, `robots.txt` (fetched through plan-02's
`safe_fetch`) and a per-mission fetch budget, and records every skip with its reason. Nothing here produces knowledge:
it produces URLs with provenance for the Internet agent, whose pages carry authority INTERNET_RESEARCH.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from ka import config
from ka.extraction import normalize
from ka.security import is_safe_url
from ka.timeutil import now_iso

USER_AGENT = "enterprise-os-ka"
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$)", re.I)


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""
    publisher: str | None = None
    published_at: str | None = None
    query: str = ""
    rank: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "title": self.title, "snippet": self.snippet, "publisher": self.publisher,
                "published_at": self.published_at, "query": self.query, "rank": self.rank}


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> list[SearchResult]: ...


class NullSearchProvider:
    name = "none"

    def search(self, query: str, *, limit: int) -> list[SearchResult]:
        return []


class FixtureSearchProvider:
    """A JSON file `{query: [{url, title, snippet, publisher, published_at}]}`; exact query first, then token overlap."""
    name = "fixture"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, list[dict[str, Any]]] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def search(self, query: str, *, limit: int) -> list[SearchResult]:
        rows = self.data.get(query)
        if rows is None:
            q = set(normalize(query).split())
            best, score = None, 0.0
            for k, v in self.data.items():
                kt = set(normalize(k).split())
                s = len(q & kt) / (len(q | kt) or 1)
                if s > score:
                    best, score = v, s
            rows = best if score >= 0.3 else []
        return [SearchResult(url=r["url"], title=r.get("title", ""), snippet=r.get("snippet", ""), publisher=r.get("publisher"),
                             published_at=r.get("published_at"), query=query, rank=i + 1) for i, r in enumerate(rows[:limit])]


def select_provider() -> tuple[SearchProvider, str | None]:
    """The configured provider, failing closed to `none` with a note on an unknown value."""
    choice = (config.get("KA_SEARCH_PROVIDER") or "none").strip().lower()
    if choice == "fixture":
        return FixtureSearchProvider(config.get("KA_SEARCH_FIXTURE") or ""), None
    if choice == "none":
        return NullSearchProvider(), None
    return NullSearchProvider(), f"unknown KA_SEARCH_PROVIDER {choice!r}; failing closed to none"


def canonical_url(url: str) -> str:
    u = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not _TRACKING.match(k)])
    path = u.path or "/"
    return urlunparse((u.scheme.lower(), u.netloc.lower(), path, "", query, ""))


class RobotsCache:
    """robots.txt per host, fetched once per run through `safe_fetch`; unreachable → allowed, recorded."""

    def __init__(self, fetch: Callable[..., Any] | None = None, user_agent: str = USER_AGENT):
        self._fetch, self.user_agent = fetch, user_agent
        self._parsers: dict[str, RobotFileParser | None] = {}
        self.notes: list[str] = []

    def allowed(self, url: str) -> tuple[bool, str]:
        u = urlparse(url)
        host = f"{u.scheme}://{u.netloc}"
        if host not in self._parsers:
            rp = RobotFileParser()
            try:
                import ka.security as _sec                      # resolved at call time so a test can patch safe_fetch
                got = (self._fetch or _sec.safe_fetch)(f"{host}/robots.txt", timeout=10)
                rp.parse(got.content.decode("utf-8", errors="replace").splitlines())
                self._parsers[host] = rp
            except Exception as e:  # noqa: BLE001 — unreachable robots counts as allowed, and is recorded
                self._parsers[host] = None
                self.notes.append(f"{host}: robots.txt unreachable ({type(e).__name__}); treated as allowed")
        rp = self._parsers[host]
        if rp is None:
            return True, "robots unreachable; allowed"
        ok = rp.can_fetch(self.user_agent, url)
        return ok, "robots allows" if ok else "robots disallows"


@dataclass
class Selection:
    selected: list[SearchResult] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    considered: int = 0


class DiscoveryAgent:
    """First in the coordinator: produces `ctx.discovered` and `ctx.run.discovery`; yields no findings of its own."""
    agent_id = "agent.discovery"

    def __init__(self, provider: SearchProvider | None = None, robots: RobotsCache | None = None, provider_note: str | None = None):
        if provider is None:
            provider, provider_note = select_provider()
        self.provider, self.robots, self.provider_note = provider, robots or RobotsCache(), provider_note

    @staticmethod
    def queries_for(mission) -> list[str]:
        out: list[str] = []
        for q in [mission.objective] + list(mission.research_questions):
            q = " ".join(str(q).split())[:200]
            if q and not q.startswith("http") and q not in out:
                out.append(q)
        return out

    def select(self, objective: str, results: list[SearchResult], *, budget: int, allowed_domains: set[str], respect_robots: bool) -> Selection:
        sel = Selection(considered=len(results))
        obj = set(normalize(objective).split())
        seen: set[str] = set()
        scored: list[tuple[float, int, SearchResult]] = []
        for r in results:
            cu = canonical_url(r.url)
            if cu in seen:
                sel.skipped.append({"url": r.url, "reason": "duplicate of a result already considered"})
                continue
            seen.add(cu)
            host = (urlparse(cu).hostname or "").lower()
            if allowed_domains and not any(host == d or host.endswith("." + d) for d in allowed_domains):
                sel.skipped.append({"url": cu, "reason": "domain not allowed"})
                continue
            ok, why = is_safe_url(cu)
            if not ok:
                sel.skipped.append({"url": cu, "reason": f"unsafe url: {why}"})
                continue
            if respect_robots:
                ok, why = self.robots.allowed(cu)
                if not ok:
                    sel.skipped.append({"url": cu, "reason": "robots"})
                    continue
            overlap = len(obj & set(normalize(r.title + " " + r.snippet).split())) / (len(obj) or 1)
            r.url = cu
            scored.append((overlap, -r.rank, r))
        scored.sort(key=lambda t: (-t[0], -t[1]))
        for i, (_, _, r) in enumerate(scored):
            if i < budget:
                sel.selected.append(r)
            else:
                sel.skipped.append({"url": r.url, "reason": "budget"})
        return sel

    def research(self, ctx) -> list:
        budget = config.get("KA_DISCOVERY_BUDGET")
        allowed = {d.strip().lower() for d in (config.get("KA_ALLOWED_DOMAINS") or "").split(",") if d.strip()}
        gate = bool(config.get("KA_RESEARCH_INTERNET"))
        respect = bool(config.get("KA_RESPECT_ROBOTS")) and gate      # gate off → no network at all, robots included
        disc: dict[str, Any] = {"provider": self.provider.name, "queries": [], "results": 0, "selected": [], "fetched": [], "skipped": [],
                                "notes": [], "budget": budget, "robots": respect, "allowed_domains": sorted(allowed)}
        if self.provider_note:
            disc["notes"].append(self.provider_note)
        if self.provider.name == "none":
            disc["notes"].append("no search provider (Q5)")
        results: list[SearchResult] = []
        for q in self.queries_for(ctx.mission):
            disc["queries"].append(q)
            try:
                results += self.provider.search(q, limit=config.get("KA_DISCOVERY_RESULTS"))
            except Exception as e:  # noqa: BLE001 — a failing provider must not lose the other agents
                ctx.run.errors.append(f"{self.agent_id}: {type(e).__name__}: {e}")
                disc["notes"].append(f"provider failed on {q!r}: {type(e).__name__}")
        sel = self.select(ctx.mission.objective, results, budget=budget, allowed_domains=allowed, respect_robots=respect)
        disc["results"] = sel.considered
        disc["notes"] += self.robots.notes
        if gate and not respect and sel.selected:
            disc["notes"].append("robots.txt ignored (KA_RESPECT_ROBOTS=0)")
        if not gate:
            for r in sel.selected:
                disc["skipped"].append({"url": r.url, "reason": "gate off (KA_RESEARCH_INTERNET=0)"})
            disc["selected"] = [r.as_dict() for r in sel.selected]
            ctx.discovered = []
        else:
            disc["selected"] = [r.as_dict() for r in sel.selected]
            ctx.discovered = list(sel.selected)
        disc["skipped"] += sel.skipped
        disc["recorded_at"] = now_iso()
        ctx.run.discovery = disc
        return []
# [/block plan-07]
