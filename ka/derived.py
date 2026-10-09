# [block plan-22]
"""Nugget versions as immutable derived artefacts (research-03 R6). A service subscriber on the `knowledge.*` events governance already
emits builds the note's payload for the version AS IT IS at that moment and queues `put_derived` on the plan-20 outbox under the key
`ka:<tenant>:nugget:<canonical>:<version>:<status>` — one artefact per (canonical_id, version, status), never an overwrite, never a
second approval path (governance is protected and untouched). On the local backend the outbox runs synchronously so the derived JSON
lands beside the objects; on the Data Platform backend the worker delivers it with retry."""
from __future__ import annotations

import json
from typing import Any

from ka import __version__, config
from ka.model import DerivedArtefact, KnowledgeNuggetVersion, PendingOp
from ka.physical import PhysicalRef
from ka.timeutil import now_iso

PUBLISH_ON = ("knowledge.candidate.created", "knowledge.approved", "knowledge.rejected", "knowledge.superseded")


def artefact_key(tenant: str, v: KnowledgeNuggetVersion) -> str:
    return f"ka:{tenant}:nugget:{v.canonical_id}:{v.version}:{v.status.value}"


def build_payload(repo, v: KnowledgeNuggetVersion) -> dict[str, Any]:
    """The note's list (research-03 §6): interpretation, status, authority, evidence spans, source/DP ids, versions, correlation ids.
    Ids and text only — no token, no filesystem path."""
    sources, ext_versions = [], {}
    for sid in v.source_refs:
        src = repo.sources.get(sid)
        if src is None:
            continue
        ver = repo.source_versions.get(src.current_version_id or "")
        b = repo.binding_for_version(ver.id) if ver is not None else None
        sources.append({"source_id": sid, "source_version_id": ver.id if ver else None, "version": ver.version if ver else None,
                        "dp_asset_id": b.dp_asset_id if b else None, "dp_asset_version_id": b.dp_asset_version_id if b else None,
                        "sha256": ver.checksum if ver else None, "authority_type": src.authority_type.value, "visibility": src.visibility.value})
        if ver is not None:
            ext_versions[ver.id] = ver.extraction_version
    evidence = []
    for eid in v.evidence_refs:
        e = repo.evidence.get(eid)
        if e is None:
            continue
        b = repo.binding_for_version(e.source_version_id)
        evidence.append({"id": e.id, "source_id": e.source_id, "source_version_id": e.source_version_id, "span_id": e.span_id, "start": e.start,
                         "end": e.end, "locator": e.locator, "excerpt": e.excerpt, "dp_asset_id": b.dp_asset_id if b else None,
                         "dp_asset_version_id": b.dp_asset_version_id if b else None})
    gb = repo.binding_for(v.ref)
    return {
        "canonical_id": v.canonical_id, "version": v.version, "ref": v.ref, "title": v.title, "statement": v.statement,
        "normalized_meaning": v.normalized_meaning, "knowledge_type": v.knowledge_type.value,
        "subject": v.subject.model_dump(mode="json") if v.subject else None, "predicate": v.predicate,
        "object": v.object.model_dump(mode="json") if v.object else None,
        "binding": {"status": gb.status.value if gb and hasattr(gb.status, "value") else (gb.status if gb else None), "digest": gb.digest if gb else None},
        "status": v.status.value, "authority_type": v.authority_type.value, "authority_rank": v.authority_rank, "confidence": v.confidence,
        "effective_from": v.effective_from, "effective_to": v.effective_to, "scope": v.scope.key(), "visibility": v.visibility.value,
        "sources": sources, "evidence": evidence, "extraction_versions": ext_versions, "research_run_refs": list(v.research_run_refs),
        "governance_decision_id": v.governance_decision_id, "graph_change_refs": list(v.graph_change_refs),
        "derived_graph_refs": [g.model_dump(mode="json") for g in v.derived_graph_refs],
        "supersedes": v.supersedes, "superseded_by": v.superseded_by, "created_at": v.created_at, "created_by": v.created_by,
        "approved_at": v.approved_at, "approved_by": v.approved_by, "channel": v.channel.value, "ka_version": __version__,
    }


class DerivedPublisher:
    def __init__(self, repo, bus, auditor, outbox, physical):
        self.repo, self.bus, self.auditor, self.outbox, self.physical = repo, bus, auditor, outbox, physical
        outbox.handlers["put_derived"] = self._put_derived
        for name in PUBLISH_ON:
            bus.subscribe(name, lambda ev, _n=name: self.publish(ev.get("ref"), event=_n))

    # ---- subscriber --------------------------------------------------------------------------------------------

    def publish(self, ref: str | None, *, event: str) -> DerivedArtefact | None:
        v = self.repo.version(ref or "")
        if v is None:
            return None
        tenant = config.get("KA_TENANT_ID")
        key = artefact_key(tenant, v)
        existing = self.repo.derived_artefacts.where(lambda a: a.idempotency_key == key)
        if existing:
            return existing[0]                                            # immutable per key: a replay is a no-op
        payload = build_payload(self.repo, v)
        art = DerivedArtefact(canonical_id=v.canonical_id, version=v.version, status=v.status.value, ref=v.ref, idempotency_key=key,
                              backend=self.physical.name, event=event)
        self.repo.derived_artefacts.put(art)
        parent = next(((s["dp_asset_id"], s["dp_asset_version_id"]) for s in payload["sources"] if s["dp_asset_id"]), (None, None))
        op = self.outbox.enqueue("put_derived", key, {"artefact_id": art.id, "ref": v.ref, "payload": payload, "event": event,
                                                      "parent_asset_id": parent[0], "parent_asset_version_id": parent[1]}, by="ka.derived")
        art.op_id = op.id
        self.repo.derived_artefacts.put(art)
        if self.physical.name == "local":
            self.outbox.process_once(by="ka.derived")                     # local never needs the worker
        return self.repo.derived_artefacts.require(art.id)

    # ---- outbox handler -------------------------------------------------------------------------------------------

    def _put_derived(self, op: PendingOp) -> None:
        p = op.payload
        art = self.repo.derived_artefacts.require(p["artefact_id"])
        parent = PhysicalRef(backend=self.physical.name, asset_id=p["parent_asset_id"], asset_version_id=p["parent_asset_version_id"] or "", sha256="") if p.get("parent_asset_id") else None
        body = json.dumps(p["payload"], sort_keys=True, ensure_ascii=False).encode("utf-8")
        ref = self.physical.put_derived("nugget_version", body, parent=parent, idempotency_key=op.idempotency_key,
                                        provenance={"producer": "ka", "event": p.get("event"), "ka_version": __version__, "ref": p.get("ref")})
        art.state, art.dp_asset_id, art.dp_asset_version_id, art.sha256 = "available", ref.asset_id, ref.asset_version_id, ref.sha256
        art.parent_asset_id, art.locator, art.published_at = parent.asset_id if parent else None, ref.locator, now_iso()
        self.repo.derived_artefacts.put(art)
        self.bus.emit("physical.derived.published", artefact_id=art.id, ref=art.ref, status=art.status)

    # ---- queries ------------------------------------------------------------------------------------------------------

    def for_ref(self, ref: str) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in sorted(self.repo.derived_artefacts.where(lambda a: a.ref == ref), key=lambda a: a.created_at)]
# [/block plan-22]
