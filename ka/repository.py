"""knowledge-repository (§36): one JSON document per object under <storage_root>/<collection>/<id>.json,
mirroring enterprise-os's per-feature stores. A `Repository` bundles the collections of §37 and the
cross-object queries the services need. Governed-version immutability is enforced in ka.versioning, not
here: storage is dumb on purpose so the invariant lives in one place.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Generic, Iterable, Iterator, TypeVar

from pydantic import BaseModel

from ka import config
from ka.json_io import append_jsonl, read_json, read_jsonl, write_json
from ka.model import (
    AuditRecord,
    Connection,
    Evidence,
    DerivedArtefact,
    PendingOp,
    PhysicalBinding,
    GovernanceDecision,
    GrammarBinding,
    GraphChangeExecution,
    GraphChangeProposal,
    GraphDependency,
    KnowledgeAcquisitionRequest,
    KnowledgeCorrection,
    KnowledgeNuggetVersion,
    KnowledgeRelationship,
    PromotionProposal,
    ResearchMission,
    ResearchRun,
    Scope,
    Source,
    SourceVersion,
    SubjectRecord,
)
from ka.vocab import NuggetStatus, ScopeType

T = TypeVar("T", bound=BaseModel)


class Collection(Generic[T]):
    def __init__(self, root: Path, name: str, model: type[T], id_field: str = "id"):
        self.dir = root / name
        self.model = model
        self.id_field = id_field
        self._cache: dict[str, T] | None = None

    def _load(self) -> dict[str, T]:
        if self._cache is None:
            self._cache = {}
            if self.dir.exists():
                for p in sorted(self.dir.glob("*.json")):
                    obj = self.model.model_validate(read_json(p))
                    self._cache[getattr(obj, self.id_field)] = obj
        return self._cache

    def put(self, obj: T) -> T:
        oid = getattr(obj, self.id_field)
        write_json(self.dir / f"{oid}.json", obj.model_dump(mode="json"))
        self._load()[oid] = obj
        return obj

    def get(self, oid: str) -> T | None:
        return self._load().get(oid)

    def get_stored(self, oid: str) -> T | None:
        """Re-read from disk, bypassing the cache (the caller may hold the very object that is cached)."""
        p = self.dir / f"{oid}.json"
        return self.model.model_validate(read_json(p)) if p.exists() else None

    def require(self, oid: str) -> T:
        obj = self.get(oid)
        if obj is None:
            raise KeyError(f"{self.model.__name__} {oid!r} not found")
        return obj

    def all(self) -> list[T]:
        return list(self._load().values())

    def where(self, pred: Callable[[T], bool]) -> list[T]:
        return [o for o in self._load().values() if pred(o)]

    def __len__(self) -> int:
        return len(self._load())

    def __iter__(self) -> Iterator[T]:
        return iter(self.all())


class Repository:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else config.storage_root()
        r = self.root
        self.sources = Collection(r, "sources", Source)
        self.source_versions = Collection(r, "source_versions", SourceVersion)
        self.evidence = Collection(r, "evidence", Evidence)
        self.nuggets = Collection(r, "nuggets", KnowledgeNuggetVersion)
        self.relationships = Collection(r, "relationships", KnowledgeRelationship)
        self.decisions = Collection(r, "decisions", GovernanceDecision)
        self.corrections = Collection(r, "corrections", KnowledgeCorrection)
        self.missions = Collection(r, "missions", ResearchMission, id_field="mission_id")
        self.runs = Collection(r, "runs", ResearchRun, id_field="run_id")
        self.dependencies = Collection(r, "dependencies", GraphDependency)
        self.proposals = Collection(r, "proposals", GraphChangeProposal)
        self.executions = Collection(r, "executions", GraphChangeExecution)
        self.promotions = Collection(r, "promotions", PromotionProposal)
        self.requests = Collection(r, "requests", KnowledgeAcquisitionRequest)
        # [block plan-08]
        self.connections = Collection(r, "connections", Connection)
        # [/block plan-08]
        # [block plan-18]
        self.physical_bindings = Collection(r, "physical_bindings", PhysicalBinding)
        # [/block plan-18]
        # [block plan-20]
        self.dp_outbox = Collection(r, "dp_outbox", PendingOp)
        # [/block plan-20]
        # [block plan-22]
        self.derived_artefacts = Collection(r, "derived_artefacts", DerivedArtefact)
        # [/block plan-22]
        # [block plan-03]
        self.bindings = Collection(r, "bindings", GrammarBinding)
        self.subjects = Collection(r, "subjects", SubjectRecord, id_field="canonical_key")
        # [/block plan-03]
        self.audit_log = r / "audit.jsonl"
        self.event_log = r / "events.jsonl"

    # ---- nugget queries -------------------------------------------------------------------------

    def versions_of(self, canonical_id: str) -> list[KnowledgeNuggetVersion]:
        return sorted(self.nuggets.where(lambda n: n.canonical_id == canonical_id), key=lambda n: n.version)

    def version(self, ref: str) -> KnowledgeNuggetVersion | None:
        hits = self.nuggets.where(lambda n: n.ref == ref)
        return hits[0] if hits else None

    def stored_version(self, ref: str) -> KnowledgeNuggetVersion | None:
        cached = self.version(ref)
        return self.nuggets.get_stored(cached.id) if cached else None

    def require_version(self, ref: str) -> KnowledgeNuggetVersion:
        v = self.version(ref)
        if v is None:
            raise KeyError(f"nugget version {ref!r} not found")
        return v

    def latest_version(self, canonical_id: str) -> KnowledgeNuggetVersion | None:
        vs = self.versions_of(canonical_id)
        return vs[-1] if vs else None

    def active_version(self, canonical_id: str) -> KnowledgeNuggetVersion | None:
        for v in reversed(self.versions_of(canonical_id)):
            if v.status == NuggetStatus.ACTIVE:
                return v
        return None

    def active_nuggets(self, scope: Scope | None = None) -> list[KnowledgeNuggetVersion]:
        return self.nuggets.where(
            lambda n: n.status == NuggetStatus.ACTIVE
            and (scope is None or (n.scope_type == scope.scope_type and n.scope_id == scope.scope_id))
        )

    def nuggets_in_scope(self, scope: Scope, statuses: Iterable[NuggetStatus] | None = None) -> list[KnowledgeNuggetVersion]:
        wanted = set(statuses) if statuses else None
        return self.nuggets.where(
            lambda n: n.scope_type == scope.scope_type and n.scope_id == scope.scope_id
            and (wanted is None or n.status in wanted)
        )

    def nuggets_by_status(self, *statuses: NuggetStatus) -> list[KnowledgeNuggetVersion]:
        wanted = set(statuses)
        return self.nuggets.where(lambda n: n.status in wanted)

    def canonical_ids(self) -> list[str]:
        return sorted({n.canonical_id for n in self.nuggets})

    def next_canonical_id(self) -> str:
        nums = []
        for cid in self.canonical_ids():
            tail = cid.rsplit("-", 1)[-1]
            if tail.isdigit():
                nums.append(int(tail))
        return f"KN-{(max(nums) + 1) if nums else 1:03d}"

    def active_at(self, when_iso: str, scope: Scope | None = None) -> list[KnowledgeNuggetVersion]:
        """§14 temporal reconstruction: which versions were ACTIVE at `when`."""
        out = []
        for n in self.nuggets:
            if scope and (n.scope_type != scope.scope_type or n.scope_id != scope.scope_id):
                continue
            start = n.activated_at or n.approved_at
            if not start or start > when_iso:
                continue
            if n.status == NuggetStatus.ACTIVE:
                out.append(n)
                continue
            if n.status in {NuggetStatus.SUPERSEDED, NuggetStatus.OBSOLETE, NuggetStatus.ARCHIVED}:
                end = n.effective_to
                if end is None or end > when_iso:
                    out.append(n)
        return out

    # ---- relationships ----------------------------------------------------------------------------

    def relationships_for(self, ref: str) -> list[KnowledgeRelationship]:
        return self.relationships.where(lambda r: r.from_ref == ref or r.to_ref == ref)

    # ---- lineage --------------------------------------------------------------------------------

    def dependencies_for_nugget(self, ref: str, active_only: bool = True) -> list[GraphDependency]:
        return self.dependencies.where(lambda d: d.nugget_ref == ref and (d.active or not active_only))

    def dependencies_for_element(self, graph_id: str, element_id: str, active_only: bool = True) -> list[GraphDependency]:
        return self.dependencies.where(
            lambda d: d.graph_id == graph_id and d.element_id == element_id and (d.active or not active_only)
        )

    def evidence_for(self, version: KnowledgeNuggetVersion) -> list[Evidence]:
        return [e for e in (self.evidence.get(i) for i in version.evidence_refs) if e]

    def sources_for(self, version: KnowledgeNuggetVersion) -> list[Source]:
        return [s for s in (self.sources.get(i) for i in version.source_refs) if s]

    # ---- assertions and bindings (research-01 R2) -----------------------------------------------

    def bindings_of(self, ref: str) -> list[GrammarBinding]:
        return sorted(self.bindings.where(lambda b: b.nugget_ref == ref), key=lambda b: b.bound_at)

    def binding_for(self, ref: str) -> GrammarBinding | None:
        bs = self.bindings_of(ref)
        return bs[-1] if bs else None

    def nuggets_by_subject(self, canonical_key: str) -> list[KnowledgeNuggetVersion]:
        return self.nuggets.where(lambda n: n.subject is not None and n.subject.canonical_key == canonical_key)

    # ---- logs -----------------------------------------------------------------------------------

    def append_audit(self, rec: AuditRecord) -> None:
        append_jsonl(self.audit_log, rec.model_dump(mode="json"))

    def audit(self) -> list[AuditRecord]:
        return [AuditRecord.model_validate(r) for r in read_jsonl(self.audit_log)]

    # [block plan-18] research-03 R3: one binding per (tenant, source, version); `available` gates the version
    def binding_for_version(self, source_version_id: str) -> PhysicalBinding | None:
        hits = self.physical_bindings.where(lambda b: b.source_version_id == source_version_id)
        return hits[0] if hits else None

    def put_binding(self, b: PhysicalBinding) -> PhysicalBinding:
        same = self.physical_bindings.where(lambda x: x.tenant_id == b.tenant_id and x.ka_source_id == b.ka_source_id
                                             and x.ka_source_version == b.ka_source_version and x.id != b.id)
        if same:
            if same[0].sha256 != b.sha256:
                raise ValueError(f"binding for ({b.tenant_id}, {b.ka_source_id}, v{b.ka_source_version}) already targets sha {same[0].sha256[:12]}…; "
                                 f"a committed physical target is immutable")
            return same[0]                                   # idempotent: same key, same bytes
        return self.physical_bindings.put(b)

    def version_available(self, source_version_id: str) -> bool:
        b = self.binding_for_version(source_version_id)
        if b is not None:
            return b.status == "available"
        v = self.source_versions.get(source_version_id)      # legacy (pre-plan-18) versions: the file is the binding
        return bool(v and v.stored_path and __import__("pathlib").Path(v.stored_path).exists())
    # [/block plan-18]

    # [block plan-09] research-01 R15: events.jsonl is the outbox — every record carries a monotonic `seq` and a schema
    # `version`; records written before this plan are served with their 1-based line number so `after=` is total.
    EVENTS_VERSION = "ka-events/1"

    def _last_seq(self) -> int:
        if getattr(self, "_seq", None) is None:
            n = 0
            for i, r in enumerate(read_jsonl(self.event_log), start=1):
                n = max(n, int(r.get("seq") or i))
            self._seq = n
        return self._seq

    def append_event(self, rec: dict) -> None:
        seq = self._last_seq() + 1
        rec = {**rec, "seq": seq, "version": self.EVENTS_VERSION}
        append_jsonl(self.event_log, rec)
        self._seq = seq

    def events(self, after: int | None = None, limit: int | None = None, tail: bool = False) -> list[dict]:
        out = []
        for i, r in enumerate(read_jsonl(self.event_log), start=1):
            if "seq" not in r:
                r = {**r, "seq": i, "version": "ka-events/0"}
            if after is not None and r["seq"] <= after:
                continue
            out.append(r)
        if limit is not None:
            out = out[-limit:] if tail else out[:limit]
        return out
    # [/block plan-09]

    # ---- scope helpers --------------------------------------------------------------------------

    def known_scopes(self) -> dict[ScopeType, set[str]]:
        out: dict[ScopeType, set[str]] = {t: set() for t in ScopeType}
        for n in self.nuggets:
            out[n.scope_type].add(n.scope_id)
        for s in self.sources:
            if s.scope:
                out[s.scope.scope_type].add(s.scope.scope_id)
        return out
