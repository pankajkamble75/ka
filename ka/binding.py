# [block plan-03]
"""Grammar binder (research-01 R2): says what a nugget's assertion would become on the EOS graph — a `process_type` prop,
an edge of a known pair, a slot of the process grammar — and with what status.

    bound           the type / edge is in the loaded grammar
    proposed        bound by similarity, below exact (reasons name the match)
    unresolved      not in the grammar (alternatives listed) — EOS would report process_type.unknown
    not_applicable  the predicate compiles to a prop, not an edge (description, pre/postcondition, related_to)
    stale           the registry is stale; nothing is bound until refresh(force=True)

Bindings are records in their own collection, keyed by nugget ref + grammar versions, so a grammar release recomputes
them without touching any governed version (Inv. 3). The LLM is not consulted here: binding is a lookup, not a judgement.
"""
from __future__ import annotations

from ka.conflict import similarity
from ka.grammar import GrammarMismatch, GrammarRegistry
from ka.model import GrammarBinding, KnowledgeNuggetVersion
from ka.repository import Repository
from ka.vocab import PREDICATES, AuthorityType, BindingStatus, NuggetStatus

# predicate → (edge or None, slot or None); typed_as → props.process_type; prop-fallback predicates carry no edge.
PREDICATE_TABLE: dict[str, tuple[str | None, str | None]] = {
    "description": (None, None),
    "typed_as": (None, None),
    "decomposes_into": ("contains", "action"),
    "consumes": ("consumes", "input"),
    "produces": ("produces", "output"),
    "acts_on": ("acts_on", "entity"),
    "performed_by": ("performed_by", "actor"),
    "governed_by": ("governed_by", "rule"),
    "emits": ("emits", "event"),
    "transitions_to": ("transitions_to", "target_state"),
    "precondition": (None, "current_state"),
    "postcondition": (None, "target_state"),
    "related_to": (None, None),
}
assert set(PREDICATE_TABLE) == set(PREDICATES)


HEURISTIC_ONLY = {AuthorityType.INTERNET_RESEARCH, AuthorityType.LLM_GENERATED}   # plan-11 (Q10)


class Binder:
    def __init__(self, registry: GrammarRegistry, repo: Repository):
        self.registry, self.repo = registry, repo

    # [block plan-11] research-02 R3 (Q10): heuristic-only sources never bind without review
    def bind(self, v: KnowledgeNuggetVersion, *, method: str = "inferred") -> GrammarBinding:
        """One binding record per call. A typed assertion whose source is heuristic-only (INTERNET_RESEARCH, LLM_GENERATED)
        is capped at `proposed` until a reviewer approves the version — the approval re-bind passes method="approved"."""
        b = self._compute(v, method=method)
        if b.binding_status == BindingStatus.BOUND and v.authority_type in HEURISTIC_ONLY and method != "approved":
            b.binding_status = BindingStatus.PROPOSED
            b.reasons.append(f"heuristic-only source (Q10): {v.authority_type.value}; binds on a reviewer's approval")
        return self.repo.bindings.put(b)
    # [/block plan-11]

    def _compute(self, v: KnowledgeNuggetVersion, *, method: str = "inferred") -> GrammarBinding:
        reg = self.registry
        vers = reg.versions()
        b = GrammarBinding(nugget_ref=v.ref, grammar_version=vers["grammar_version"], type_table_version=vers["type_table_version"],
                           digest=(vers["grammar_digest"] or "")[:12] + "/" + (vers["type_table_digest"] or "")[:12], method=method)
        if v.predicate is None and v.subject is None:
            b.binding_status, b.reasons = BindingStatus.NOT_APPLICABLE, ["no assertion on this version"]
            return b
        if not reg.loaded:
            b.binding_status, b.reasons = BindingStatus.UNRESOLVED, ["no grammar loaded (set KA_GRAMMAR_DIR or KA_ENTERPRISE_OS_ROOT)"]
            return b
        if reg.is_stale():
            b.binding_status, b.reasons = BindingStatus.STALE, [reg.stale_reason() or "stale"]
            return b

        kinds = reg.node_kinds()
        if v.subject is not None and v.subject.kind not in kinds:
            b.binding_status, b.reasons = BindingStatus.UNRESOLVED, [f"subject kind {v.subject.kind!r} is not an EOS node kind ({', '.join(kinds)})"]
            return b

        pred = v.predicate or "description"
        if pred == "typed_as":
            wanted = str((v.object.value if v.object and v.object.value else (v.object.canonical_key if v.object else "")) or "").strip().lower()
            names = reg.type_names()
            if wanted in names:
                b.binding_status, b.process_type, b.confidence = BindingStatus.BOUND, wanted, 1.0
                b.reasons = [f"{wanted!r} is a type in {vers['type_table_version']}"]
            else:
                ranked = sorted(names, key=lambda n: -similarity(wanted, n) - (0.5 if n.startswith(wanted[:4]) else 0))
                best = ranked[0] if ranked else None
                score = similarity(wanted, best) if best else 0.0
                if best and (score >= 0.6 or best.startswith(wanted[:5])):
                    b.binding_status, b.process_type, b.confidence = BindingStatus.PROPOSED, best, round(max(score, 0.5), 2)
                    b.reasons = [f"{wanted!r} is not a type in {vers['type_table_version']}; closest is {best!r}"]
                else:
                    b.binding_status, b.confidence = BindingStatus.UNRESOLVED, 0.0
                    b.reasons = [f"{wanted!r} is not one of the {len(names)} types in {vers['type_table_version']}"]
                b.alternatives = ranked[:3]
            return b

        edge, slot = PREDICATE_TABLE[pred]
        if edge is None:
            b.binding_status, b.slot = BindingStatus.NOT_APPLICABLE, slot
            b.reasons = [f"{pred!r} compiles to a property, not an edge" + (f" (slot {slot})" if slot else "")]
            return b
        spec = reg.edge_spec(edge)
        if spec is None:
            b.binding_status, b.reasons = BindingStatus.UNRESOLVED, [f"edge {edge!r} is not in {vers['grammar_version']}"]
            b.alternatives = [e["name"] for e in reg.edge_pairs() if e["group"] == "process"][:3]
            return b
        b.edge, b.slot = edge, reg.slot_for_edge(edge) or slot
        b.binding_status, b.confidence = BindingStatus.BOUND, 1.0
        b.reasons = [f"{pred!r} → edge {edge!r} ({', '.join(spec.get('from', []))} → {', '.join(spec.get('to', []))}), slot {b.slot!r}"]
        if v.object is not None and v.object.kind and spec.get("to") and v.object.kind not in spec["to"]:
            b.binding_status, b.confidence = BindingStatus.PROPOSED, 0.6
            b.reasons.append(f"object kind {v.object.kind!r} is not an allowed target ({', '.join(spec['to'])})")
        return b

    def rebind_all(self) -> int:
        """After a grammar release: one new binding record per ACTIVE / PENDING version. Refuses on a stale registry."""
        if self.registry.is_stale():
            raise GrammarMismatch(self.registry.stale_reason() or "stale")
        n = 0
        for v in self.repo.nuggets_by_status(NuggetStatus.ACTIVE, NuggetStatus.PENDING_REVIEW, NuggetStatus.CONFLICT, NuggetStatus.APPROVED):
            if v.subject is None and v.predicate is None:
                continue
            # plan-11: a governed version was approved by a person — the heuristic-only cap applies to un-reviewed candidates only
            self.bind(v, method="approved" if v.status in {NuggetStatus.ACTIVE, NuggetStatus.APPROVED} else "inferred")
            n += 1
        return n
# [/block plan-03]
