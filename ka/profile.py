# [block plan-06]
"""The process profile (research-01 R12): a COMPOSED, read-only view of what KA knows about one process — description,
type (and whether it is bound), activities in document order, actors, inputs, outputs, rules, events, states — every field
pointing at its nugget and evidence, with coverage against the bound type's slot grammar and, above all, what is NOT known.

It is a query over governed versions, never a stored object (research-01 §2): ACTIVE assertions make the profile,
PENDING_REVIEW / CONFLICT ones are listed apart, everything else contributes nothing. Nothing is filled in.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ka.binding import PREDICATE_TABLE
from ka.grammar import GrammarRegistry
from ka.lineage import LineageService
from ka.model import KnowledgeNuggetVersion, Scope
from ka.repository import Repository
from ka.scope import ScopeRegistry
from ka.vocab import BindingStatus, NuggetStatus

FIELD_FOR_PREDICATE = {"performed_by": "actors", "consumes": "inputs", "produces": "outputs", "acts_on": "entities",
                       "governed_by": "rules", "emits": "events", "transitions_to": "states", "precondition": "states",
                       "postcondition": "states", "related_to": "related"}
# slot ← predicates that evidence it (the binder's table, plus the two prop-fallback slots)
PREDICATES_FOR_SLOT: dict[str, list[str]] = {}
for _pred, (_edge, _slot) in PREDICATE_TABLE.items():
    if _slot:
        PREDICATES_FOR_SLOT.setdefault(_slot, []).append(_pred)
PREDICATES_FOR_SLOT.setdefault("goal", []).append("description")
PREDICATES_FOR_SLOT.setdefault("decision", [])


class ProfileField(BaseModel):
    ref: str
    also: list[str] = Field(default_factory=list)      # other ACTIVE versions asserting the same thing (duplicates, Q11)
    statement: str
    value: str
    object_key: str | None = None
    object_kind: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    published_as: list[str] = Field(default_factory=list)
    binding_status: str | None = None


class Activity(ProfileField):
    order: int = 0
    child_key: str | None = None
    has_profile: bool = False


class ProcessProfile(BaseModel):
    key: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    description: ProfileField | None = None
    type: dict[str, Any] = Field(default_factory=lambda: {"status": "not_evidenced", "value": None})
    activities: list[Activity] = Field(default_factory=list)
    actors: list[ProfileField] = Field(default_factory=list)
    inputs: list[ProfileField] = Field(default_factory=list)
    outputs: list[ProfileField] = Field(default_factory=list)
    entities: list[ProfileField] = Field(default_factory=list)
    rules: list[ProfileField] = Field(default_factory=list)
    events: list[ProfileField] = Field(default_factory=list)
    states: list[ProfileField] = Field(default_factory=list)
    related: list[ProfileField] = Field(default_factory=list)
    pending: list[dict[str, Any]] = Field(default_factory=list)
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    coverage_note: str | None = None
    published_as: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class ProfileService:
    def __init__(self, repo: Repository, grammar: GrammarRegistry, lineage: LineageService, registry: ScopeRegistry):
        self.repo, self.grammar, self.lineage, self.registry = repo, grammar, lineage, registry

    # ---- composition ---------------------------------------------------------------------------------------

    def _field(self, v: KnowledgeNuggetVersion) -> ProfileField:
        ev = [{"evidence_id": e.id, "source_id": e.source_id, "locator": e.locator, "span_id": e.span_id, "start": e.start, "end": e.end,
               "source_title": (s.title if (s := self.repo.sources.get(e.source_id)) else None)} for e in self.repo.evidence_for(v)]
        b = self.repo.binding_for(v.ref)
        return ProfileField(ref=v.ref, statement=v.statement, value=(v.object.value or v.object.canonical_key or "") if v.object else "",
                            object_key=v.object.canonical_key if v.object else None, object_kind=v.object.kind if v.object else None,
                            evidence=ev, published_as=[f"{d.graph_id}/{d.element_id}" for d in self.lineage.where_used(v.ref)],
                            binding_status=b.binding_status.value if b else None)

    def profile(self, key: str) -> ProcessProfile:
        rec = self.repo.subjects.get(key)
        if rec is None or rec.kind != "process":
            raise KeyError(f"{key!r} is not a known process subject")
        versions = sorted(self.repo.nuggets_by_subject(key), key=lambda n: n.created_at)
        active = [v for v in versions if v.status == NuggetStatus.ACTIVE]
        pending = [v for v in versions if v.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT}]
        prof = ProcessProfile(key=key, name=rec.name, aliases=list(rec.aliases), scopes=sorted({v.scope.key() for v in active}))
        seen: dict[tuple[str, str], ProfileField] = {}                  # (predicate, object identity) → first field

        def once(pred: str, f: ProfileField) -> ProfileField | None:
            """Identical ACTIVE assertions compose once; later refs are kept on the first field as `also`."""
            k = (pred, (f.object_key or f.value or "").lower())
            if k in seen:
                seen[k].also.append(f.ref)
                return None
            seen[k] = f
            return f

        for v in active:
            pred = v.predicate or "description"
            if pred == "description":
                prof.description = self._field(v)                       # latest ACTIVE description wins
            elif pred == "typed_as":
                b = self.repo.binding_for(v.ref)
                status = b.binding_status.value if b else "unresolved"
                prof.type = {"status": status, "value": (b.process_type if (b and b.binding_status in {BindingStatus.BOUND, BindingStatus.PROPOSED}) else None),
                             "claimed": (v.object.value if v.object else None), "ref": v.ref,
                             "alternatives": list(b.alternatives) if b else [], "reasons": list(b.reasons) if b else []}
            elif pred == "decomposes_into":
                f = self._field(v)
                child = v.object.canonical_key if v.object and v.object.canonical_key else None
                a = Activity(**f.model_dump(), order=len(prof.activities) + 1, child_key=child,
                             has_profile=bool(child and self.repo.subjects.get(child) and self.repo.nuggets_by_subject(child)))
                if once(pred, a) is not None:
                    prof.activities.append(a)
            else:
                f = self._field(v)
                if once(pred, f) is not None:
                    getattr(prof, FIELD_FOR_PREDICATE.get(pred, "related")).append(f)
        if prof.description is None and active:
            first = next((v for v in active if v.predicate not in {"typed_as", "decomposes_into"}), active[0])
            prof.description = self._field(first)
        prof.pending = [{"ref": v.ref, "predicate": v.predicate, "statement": v.statement, "status": v.status.value, "scope": v.scope.key()} for v in pending]
        prof.published_as = sorted({p for v in active for p in self._field(v).published_as if "/" in p and not p.split("/", 1)[1].startswith(("contains:", "performed_by:", "consumes:", "produces:", "acts_on:", "governed_by:", "emits:", "transitions_to:"))})
        prof.coverage, prof.coverage_note = self.coverage(prof)
        prof.counts = {"assertions": len(active), "activities": len(prof.activities), "pending": len(pending),
                       "duplicates": sum(len(f.also) for f in prof.activities + prof.actors + prof.inputs + prof.outputs + prof.entities + prof.rules + prof.events + prof.states + prof.related),
                       "fields": sum(len(getattr(prof, f)) for f in ("actors", "inputs", "outputs", "entities", "rules", "events", "states", "related"))}
        return prof

    # ---- coverage against the bound type's slot grammar ------------------------------------------------

    def coverage(self, prof: ProcessProfile) -> tuple[list[dict[str, Any]], str | None]:
        if prof.type.get("status") != "bound" or not prof.type.get("value"):
            return [], "coverage needs a bound type"
        grammar = self.grammar.type_grammar(prof.type["value"]) if self.grammar.loaded else None
        if not grammar:
            return [], f"no slot grammar for type {prof.type['value']!r} in the loaded tables"
        present: dict[str, list[str]] = {}
        if prof.description:
            present.setdefault("goal", []).append("description")
        for a in prof.activities:
            present.setdefault("action", []).append("decomposes_into")
        for field_name, pred in (("actors", "performed_by"), ("inputs", "consumes"), ("outputs", "produces"), ("entities", "acts_on"),
                                 ("rules", "governed_by"), ("events", "emits")):
            if getattr(prof, field_name):
                slot = PREDICATE_TABLE[pred][1]
                present.setdefault(slot, []).append(pred)
        for f in prof.states:
            v = self.repo.version(f.ref)
            slot = PREDICATE_TABLE.get(v.predicate or "", (None, None))[1] if v else None
            if slot:
                present.setdefault(slot, []).append(v.predicate)
        out = []
        for slot, level in grammar.items():
            if level not in {"required", "recommended"}:
                continue
            via = present.get(slot, [])
            out.append({"slot": slot, "level": level, "status": "evidenced" if via else "not_evidenced", "via": sorted(set(via))})
        out.sort(key=lambda r: (0 if r["level"] == "required" else 1, r["slot"]))
        return out, None

    # ---- listing ------------------------------------------------------------------------------------------

    def list_processes(self, scope: Scope | None = None) -> list[dict[str, Any]]:
        chain = None
        if scope is not None:
            chain = {scope.key()} | {s.key() for s in self.registry.ancestors(scope)}
        out = []
        for rec in self.repo.subjects.where(lambda r: r.kind == "process"):
            vs = self.repo.nuggets_by_subject(rec.canonical_key)
            active = [v for v in vs if v.status == NuggetStatus.ACTIVE]
            if not active:
                continue                      # a child named by a decomposition is a subject, not yet a profile
            if chain is not None and not any(v.scope.key() in chain for v in active):
                continue
            typed = next((v for v in active if v.predicate == "typed_as"), None)
            b = self.repo.binding_for(typed.ref) if typed else None
            out.append({"key": rec.canonical_key, "name": rec.name, "aliases": list(rec.aliases), "assertions": len(active),
                        "activities": sum(1 for v in active if v.predicate == "decomposes_into"),
                        "pending": sum(1 for v in vs if v.status in {NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT}),
                        "type": {"status": b.binding_status.value if b else "not_evidenced", "value": b.process_type if b else None},
                        "scopes": sorted({v.scope.key() for v in active})})
        return sorted(out, key=lambda r: r["name"].lower())
# [/block plan-06]
