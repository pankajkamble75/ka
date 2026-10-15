# [block plan-36]
"""Synthetic demo knowledge for the NEXOS Cloud Run MVP: Copper Kettle Coffee, a fictional single-site café.

    knowledge-acquisition seed-demo copper-kettle [STORAGE_DIR]

Every document below is SYNTHETIC (invented for the demo; no real business, prices or people). The seed goes through KA's own
governed flow, exactly as an upload in the console does: `IngestionService.upload` (source + version + physical binding + audit)
→ `GovernanceService.extract_from_source` (evidence + candidate nuggets through `ingest_candidate`, the one pipeline) →
`GovernanceService.decide(APPROVE)` by a named reviewer (decision record, ACTIVE version, lineage). Nothing is written directly.

Scope: the nuggets live on INSTANCE `copper_kettle_coffee` under DOMAIN `coffee-shop` (Knowledge Worker's instance and
substructure ids, graphs/instances/copper_kettle_coffee). KA's search filters by exact scope and prefers `instance_id` over
`domain_id`, so Knowledge Worker's `POST /v1/knowledge/search {query, instance_id: "copper_kettle_coffee", ...}` finds them.

Idempotent: each document is uploaded under a fixed location; an unchanged document is not re-ingested (same checksum) and a
source whose candidates already exist is not re-extracted, so a second run adds no source version, nugget or decision. A
candidate left pending by an interrupted run is approved on the next run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ka.model import Scope
from ka.vocab import AuthorityType, DecisionOutcome, NuggetStatus, ScopeType

DATASET = "copper-kettle"
OWNER = "nexos-demo-seed"
REVIEWER = "copper-kettle-owner (synthetic)"

STRUCTURE = Scope(scope_type=ScopeType.STRUCTURE, scope_id="universal")
DOMAIN = Scope(scope_type=ScopeType.DOMAIN, scope_id="coffee-shop")
INSTANCE = Scope(scope_type=ScopeType.INSTANCE, scope_id="copper_kettle_coffee")

# No headings and no normative word in the banner: the extraction passes then yield exactly the policy sentences (a heading such as
# "Review" or "Approval" would add a process-description candidate that duplicates a rule).
_BANNER = ("SYNTHETIC DEMO DATA for the NEXOS MVP. Copper Kettle Coffee is a fictional single-site cafe; "
           "its policies, numbers and names are invented.\n\n")

# (slug, title, body). Each policy sentence uses a normative verb so the extraction pass (LLM or heuristic) yields one nugget per rule.
DOCUMENTS: list[tuple[str, str, str]] = [
    ("01-target-margins", "Target Margin and Pricing Rule Definition",
     "Espresso drink menu prices must keep ingredient and cup cost at or below 25% of the menu price.\n\n"
     "Pastry and baked-goods menu prices must keep food cost at or below 32% of the menu price.\n\n"
     "Retail coffee bean bags must be priced at a markup of at least 60% over landed bean cost.\n"),
    ("02-competitor-benchmarking", "Local Competitor Price Benchmarking",
     "Before each quarterly price review the manager must record the prices of a latte, a drip coffee and a croissant "
     "at three nearby independent cafes.\n\n"
     "A Copper Kettle menu price should stay within 10% of the local competitor median for the same item unless the owner "
     "approves an exception.\n"),
    ("03-quarterly-review", "Quarterly Menu Price Review Cadence",
     "Menu prices must be reviewed once per quarter, in the first week of January, April, July and October.\n\n"
     "Menu price changes agreed in a quarterly review take effect on the first Monday after the owner approves them.\n"),
    ("04-supplier-pass-through", "Supplier Cost Pass-Through Rule",
     "When a supplier raises an ingredient cost by more than 5%, the affected menu prices must be re-checked against "
     "the category cost targets within 14 days.\n\n"
     "A supplier cost increase below 5% should be absorbed until the next quarterly menu price review.\n"),
    ("05-seasonal-specials", "Seasonal Specials Pricing",
     "A seasonal special drink must be priced at least $0.50 above the closest standard espresso drink on the menu.\n\n"
     "A seasonal special must leave the menu after 12 weeks unless its price is re-approved by the owner.\n"),
    ("06-rounding", "Menu Price Rounding Rule",
     "Every calculated menu price must be rounded up to the nearest $0.25 before it is published on the menu board.\n"),
    ("07-owner-approval", "Menu Item Price Setting and Approval",
     "Every menu price change requires written approval by the owner before it is printed on the menu board or entered in the till.\n\n"
     "The shift manager may not change a menu price without the owner's approval.\n"),
]


def _register_scopes(ka) -> None:
    for scope, parent, name in [(STRUCTURE, None, "Structure"), (DOMAIN, STRUCTURE, "Coffee Shop"),
                                (INSTANCE, DOMAIN, "Copper Kettle Coffee (synthetic)")]:
        if ka.registry.names.get(scope.key()) != name or ka.registry.parent_of(scope) != parent:
            ka.register_scope(scope, parent, name)


def seed_copper_kettle(ka) -> dict[str, Any]:
    """Seed the dataset into an existing `KnowledgeAcquisition`. Returns what was created, skipped and is now ACTIVE."""
    _register_scopes(ka)
    report: dict[str, Any] = {"dataset": DATASET, "scope": INSTANCE.key(), "sources_new": 0, "sources_unchanged": 0,
                              "candidates_extracted": 0, "approved": 0, "active_refs": []}
    for slug, title, body in DOCUMENTS:
        got = ka.ingestion.upload(filename=f"copper-kettle-coffee/{slug}.md", data=(_BANNER + body).encode(),
                                  owner=OWNER, scope=INSTANCE, title=f"Copper Kettle Coffee - {title} (SYNTHETIC)",
                                  authority=AuthorityType.APPROVED_ENTERPRISE_POLICY, author="Copper Kettle Coffee owner (synthetic)")
        src, ver = got.source, got.version
        from_this_version = {e.id for e in ka.repo.evidence.where(lambda e, _v=ver.id: e.source_version_id == _v)}
        mine = ka.repo.nuggets.where(lambda n, _s=src.id: _s in n.source_refs and bool(from_this_version & set(n.evidence_refs)))
        if mine:
            report["sources_unchanged"] += 1
        else:
            report["sources_new"] += 1
            mine = ka.governance.extract_from_source(src, ver, got.extraction, actor=OWNER)
            report["candidates_extracted"] += len(mine)
        for n in mine:
            cur = ka.repo.version(n.ref)
            if cur is not None and cur.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.ANALYZED, NuggetStatus.CONFLICT}:
                ka.governance.decide(cur.ref, DecisionOutcome.APPROVE, by=REVIEWER,
                                     reason=f"Synthetic demo seed ({DATASET}): owner-approved pricing policy '{title}'")
                report["approved"] += 1
    report["active_refs"] = sorted(n.ref for n in ka.repo.active_nuggets(INSTANCE))
    return report


DATASETS = {DATASET: seed_copper_kettle}


def seed(dataset: str, storage: str | Path | None = None) -> dict[str, Any]:
    """CLI entry: open the store (no background workers, deterministic offline extraction) and seed `dataset`."""
    from ka import config
    from ka.llm import StubLLMProvider
    from ka.service import KnowledgeAcquisition
    if dataset not in DATASETS:
        raise SystemExit(f"unknown demo dataset {dataset!r}; known: {', '.join(sorted(DATASETS))}")
    root = Path(storage) if storage else config.storage_root()
    # The stub provider makes the extraction deterministic and needs no outbound call (the heuristic pass).
    ka = KnowledgeAcquisition(root, provider=StubLLMProvider(), start_workers=False)
    out = DATASETS[dataset](ka)
    out["storage"] = str(ka.repo.root)
    return out
# [/block plan-36]
