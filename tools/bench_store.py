#!/usr/bin/env python
# [block plan-09]
"""research-01 R16 (benchmark half): measure the JSON-per-object store before anyone proposes — or dismisses — a migration.

    .venv/bin/python tools/bench_store.py 10000 [--root DIR] [--out docs/research/benchmarks/store-bench-<date>.md]

Fills a fresh repository with N nugget versions across 20 scopes (one source per 100 nuggets), then times, each once:
cold load of the nuggets collection (fresh process state), `nuggets_by_status(ACTIVE)` on the warm cache,
`active_nuggets(scope)`, one `search.search` query, one `put` and one `get`. Prints a Markdown row; `--out` appends it.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ka.model import KnowledgeNuggetVersion, Scope, Source  # noqa: E402
from ka.repository import Repository  # noqa: E402
from ka.search import SearchService  # noqa: E402
from ka.vocab import AuthorityType, KnowledgeType, NuggetStatus, ScopeType, SourceType  # noqa: E402

WORDS = "refund approval manager merchant chargeback settlement dispute window risk score committee threshold".split()


def fill(root: Path, n: int) -> float:
    repo = Repository(root)
    scopes = [Scope(scope_type=ScopeType.DOMAIN if i % 2 else ScopeType.INSTANCE, scope_id=f"scope-{i}") for i in range(20)]
    t0 = time.perf_counter()
    src_id = None
    for i in range(n):
        if i % 100 == 0:
            s = Source(title=f"doc {i // 100}", source_type=SourceType.MARKDOWN, owner="bench", scope=scopes[i % 20], checksum=f"{i:064x}")
            repo.sources.put(s)
            src_id = s.id
        words = " ".join(WORDS[(i + k) % len(WORDS)] for k in range(6))
        sc = scopes[i % 20]
        v = KnowledgeNuggetVersion(canonical_id=f"KN-{i:06d}", version=1, title=f"nugget {i}", statement=f"Rule {i}: {words} above ${i % 5000}.",
                                   knowledge_type=KnowledgeType.RULE, scope_type=sc.scope_type, scope_id=sc.scope_id,
                                   authority_type=AuthorityType.PROJECT_DOCUMENTATION,
                                   status=NuggetStatus.ACTIVE if i % 3 else NuggetStatus.PENDING_REVIEW, created_by="bench", source_refs=[src_id])
        repo.nuggets.put(v)
    return time.perf_counter() - t0


def timed(fn):
    t0 = time.perf_counter()
    r = fn()
    return r, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(tempfile.mkdtemp(prefix="ka-bench-"))
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    fill_s = fill(root, a.n)
    du = sum(p.stat().st_size for p in root.rglob("*.json")) / 1e6
    repo = Repository(root)                                             # fresh object → cold cache
    _, cold = timed(lambda: repo.nuggets.all())
    _, by_status = timed(lambda: repo.nuggets_by_status(NuggetStatus.ACTIVE))
    _, active = timed(lambda: repo.active_nuggets(Scope(scope_type=ScopeType.DOMAIN, scope_id="scope-1")))
    hits, search = timed(lambda: SearchService(repo).search("refund approval manager", limit=50))
    v = repo.nuggets.all()[0]
    _, put = timed(lambda: repo.nuggets.put(v))
    _, get = timed(lambda: repo.nuggets.get(v.id))
    # [block plan-25] research-04 R13: the wiki projection of the largest scope, and wiki search, at this size
    from ka.lineage import LineageService
    from ka.profile import ProfileService
    from ka.grammar import GrammarRegistry
    from ka.scope import ScopeRegistry
    from ka.wiki import WikiService
    from ka.llm import StubLLMProvider
    reg = ScopeRegistry()
    for i in range(20):
        reg.register(Scope(scope_type=ScopeType.DOMAIN if i % 2 else ScopeType.INSTANCE, scope_id=f"scope-{i}"))
    wiki = WikiService(repo, ProfileService(repo, GrammarRegistry.from_config(root), LineageService(repo), reg), reg, LineageService(repo), StubLLMProvider())
    art, wiki_article = timed(lambda: wiki.article("scope:DOMAIN|scope-1"))
    whits, wiki_search = timed(lambda: wiki.search("refund approval manager"))
    # [/block plan-25]
    row = (f"| {a.n} | {fill_s:.1f} | {du:.1f} | {cold:.2f} | {by_status * 1000:.0f} | {active * 1000:.0f} | {search * 1000:.0f} "
           f"| {put * 1000:.1f} | {get * 1000:.2f} | {len(hits)} | {wiki_article * 1000:.0f} ({len(art['refs'])} refs) | {wiki_search * 1000:.0f} |")
    header = ("| N nuggets | fill s | size MB | cold load s | by_status ms | active(scope) ms | search ms | put ms | get ms | hits | wiki article ms | wiki search ms |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|---|")
    print(header)
    print(row)
    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(f"# Store benchmark — JSON per object (research-01 R16, plan-09)\n\nMachine: this VPS; Python {sys.version.split()[0]}; one run each, no warm-up.\n\n{header}\n", encoding="utf-8")
        with p.open("a", encoding="utf-8") as f:
            f.write(row + "\n")
    if not a.root:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
# [/block plan-09]
