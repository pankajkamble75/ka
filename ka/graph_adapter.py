"""§39 — adapter around the Enterprise OS graph. KA never touches graph storage directly; every read and
write goes through this protocol so the graph implementation can change underneath.

Two implementations:
  * `InMemoryGraphAdapter` — the reference implementation and test double. It models the one inheritance
    mechanism enterprise-os has (an instance realizes a domain element by copy, marked `props.realizes`)
    and derives §9 inheritance states by comparing the copy with its parent.
  * `EnterpriseOSGraphAdapter` — wraps `knowledge_worker.graph_store.GraphStore` (v2 graph model), where a
    Domain is a `substructure`, an Instance pins substructure versions, and nodes/edges carry only `props`
    as an extension point. Lineage metadata (§40) is written to `props.knowledge_lineage`.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ka.model import ElementChange, Scope
from ka.vocab import GraphElementKind, InheritanceState, ScopeType

LINEAGE_KEY = "knowledge_lineage"


class GraphElement(BaseModel):
    graph_id: str
    element_id: str
    kind: GraphElementKind
    name: str = ""
    description: str = ""
    props: dict[str, Any] = Field(default_factory=dict)
    scope: Scope
    source: str | None = None       # for edges
    target: str | None = None

    def lineage(self) -> list[dict[str, Any]]:
        return list(self.props.get(LINEAGE_KEY, []))

    def realizes(self) -> dict[str, Any] | None:
        return self.props.get("realizes")


class GraphAdapter(Protocol):
    def graph_id_for(self, scope: Scope) -> str: ...
    def scope_for_graph(self, graph_id: str) -> Scope: ...
    def get_graph_element(self, graph_id: str, element_id: str) -> GraphElement | None: ...
    def get_graph_lineage(self, graph_id: str, element_id: str) -> list[dict[str, Any]]: ...
    def list_elements(self, scope: Scope) -> list[GraphElement]: ...
    def find_elements_by_knowledge_nugget(self, nugget_id: str, version: int | None = None) -> list[GraphElement]: ...
    def find_descendants(self, scope: Scope) -> list[Scope]: ...
    def calculate_inheritance(self, scope: Scope) -> dict[str, InheritanceState]: ...
    def validate_change(self, changes: list[ElementChange]) -> list[dict[str, Any]]: ...
    def apply_change(self, changes: list[ElementChange]) -> None: ...
    def rollback_change(self, changes: list[ElementChange]) -> None: ...
    # plan-05: publication through the store's own lifecycle (block below)
    def publish(self, scope: Scope, changes: list[ElementChange], *, actor: str, reason: str, base_version: str | None,
                rollback: bool = False) -> PublishResult: ...
    def base_version(self, scope: Scope) -> str | None: ...
    def resolve_element_id(self, scope: Scope, local_id: str) -> str: ...
    def edge_target_kind(self, edge: str) -> str | None: ...
    def needs_named_actor(self) -> bool: ...


class GraphValidationError(RuntimeError):
    pass


# plan-05: publication types (the plan-05 block is the EOS adapter's publish below)
class PublishRefused(RuntimeError):
    """The target graph store refused the publication (EOS `ProposalRefused` / `GraphRejected`, or the in-memory validator)."""

    def __init__(self, code: str, detail: str, findings: list[Any] | None = None):
        super().__init__(detail)
        self.code, self.detail, self.findings = code, detail, findings or []


class PublishResult(BaseModel):
    applied: bool = True
    eos_proposal_id: str | None = None
    eos_status: str | None = None
    new_version: str | None = None
    pinned_instances: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ====================================================================== in-memory reference adapter


class InMemoryGraphAdapter:
    """Reference adapter. With `path` it persists itself as one JSON file after every write, so the
    standalone server keeps its shadow graph across restarts."""

    def __init__(self, path: "Path | None" = None) -> None:
        self.graphs: dict[str, dict[str, GraphElement]] = {}
        self._scope_of: dict[str, Scope] = {}
        self._graph_of: dict[str, str] = {}
        self._children: dict[str, list[str]] = {}      # graph_id → child graph ids (instances of a domain)
        self._parent: dict[str, str] = {}
        self._path = path
        if path is not None and path.exists():
            self._load()

    # ---- persistence ------------------------------------------------------------------------------------

    def _save(self) -> None:
        if self._path is None:
            return
        from ka.json_io import write_json
        write_json(self._path, {
            "graphs": {g: {eid: el.model_dump(mode="json") for eid, el in els.items()} for g, els in self.graphs.items()},
            "scope_of": {g: s.model_dump() for g, s in self._scope_of.items()},
            "parent": self._parent,
        })

    def _load(self) -> None:
        from ka.json_io import read_json
        data = read_json(self._path)
        self._scope_of = {g: Scope(**s) for g, s in data.get("scope_of", {}).items()}
        self._graph_of = {s.key(): g for g, s in self._scope_of.items()}
        self._parent = dict(data.get("parent", {}))
        for g, p in self._parent.items():
            self._children.setdefault(p, []).append(g)
        self.graphs = {g: {eid: GraphElement(**el) for eid, el in els.items()} for g, els in data.get("graphs", {}).items()}

    # ---- setup helpers (tests / demos) --------------------------------------------------------------

    def add_graph(self, scope: Scope, graph_id: str | None = None, parent: Scope | None = None) -> str:
        gid = graph_id or scope.scope_id
        self.graphs.setdefault(gid, {})
        self._scope_of[gid] = scope
        self._graph_of[scope.key()] = gid
        if parent is not None:
            pg = self._graph_of[parent.key()]
            if gid not in self._children.setdefault(pg, []):
                self._children[pg].append(gid)
            self._parent[gid] = pg
        self._save()
        return gid

    def put_element(self, el: GraphElement) -> GraphElement:
        self.graphs.setdefault(el.graph_id, {})[el.element_id] = el
        self._save()
        return el

    def realize(self, domain_scope: Scope, instance_scope: Scope) -> int:
        """Copy every domain element into the instance with props.realizes (how enterprise-os inherits)."""
        dg, ig = self._graph_of[domain_scope.key()], self._graph_of[instance_scope.key()]
        n = 0
        for el in self.graphs[dg].values():
            local_id = f"{dg}/{el.element_id}"
            if local_id in self.graphs[ig]:
                continue
            cp = el.model_copy(deep=True)
            cp.graph_id, cp.element_id, cp.scope = ig, local_id, instance_scope
            cp.props["realizes"] = {"graph_id": dg, "element_id": el.element_id}
            self.graphs[ig][local_id] = cp
            n += 1
        self._save()
        return n

    # ---- protocol -------------------------------------------------------------------------------------

    def graph_id_for(self, scope: Scope) -> str:
        if scope.key() not in self._graph_of:
            self.add_graph(scope)
        return self._graph_of[scope.key()]

    def scope_for_graph(self, graph_id: str) -> Scope:
        return self._scope_of[graph_id]

    def get_graph_element(self, graph_id, element_id):
        return self.graphs.get(graph_id, {}).get(element_id)

    def get_graph_lineage(self, graph_id, element_id):
        el = self.get_graph_element(graph_id, element_id)
        return el.lineage() if el else []

    def list_elements(self, scope):
        return list(self.graphs.get(self._graph_of.get(scope.key(), ""), {}).values())

    def find_elements_by_knowledge_nugget(self, nugget_id, version=None):
        out = []
        for g in self.graphs.values():
            for el in g.values():
                for ln in el.lineage():
                    if ln.get("nugget_id") == nugget_id and (version is None or ln.get("version") == version):
                        out.append(el)
                        break
        return out

    def find_descendants(self, scope):
        gid = self._graph_of.get(scope.key())
        out: list[Scope] = []
        stack = list(self._children.get(gid, [])) if gid else []
        while stack:
            g = stack.pop()
            out.append(self._scope_of[g])
            stack.extend(self._children.get(g, []))
        return out

    def calculate_inheritance(self, scope):
        """§9 states for every element of `scope`'s graph, relative to what it realizes."""
        states: dict[str, InheritanceState] = {}
        gid = self._graph_of.get(scope.key())
        if not gid:
            return states
        realized_parents: set[tuple[str, str]] = set()
        parent_gid = self._parent.get(gid)
        for el in self.graphs[gid].values():
            r = el.realizes()
            if not r:
                states[el.element_id] = InheritanceState.LOCALLY_EXTENDED
                continue
            parent_gid = parent_gid or r["graph_id"]
            realized_parents.add((r["graph_id"], r["element_id"]))
            parent = self.get_graph_element(r["graph_id"], r["element_id"])
            if parent is None:
                states[el.element_id] = InheritanceState.CONFLICTING
                continue
            states[el.element_id] = _compare(parent, el)
        # Parent elements that have no copy here were locally removed.
        if parent_gid:
            for pel in self.graphs.get(parent_gid, {}).values():
                if (parent_gid, pel.element_id) not in realized_parents:
                    states[f"{parent_gid}/{pel.element_id}"] = InheritanceState.LOCALLY_REMOVED
        return states

    def validate_change(self, changes):
        results = []
        for c in changes:
            ok, why = True, "ok"
            el = self.get_graph_element(c.graph_id, c.element_id)
            if c.operation == "create" and el is not None:
                ok, why = False, "element already exists"
            elif c.operation in {"update", "remove"} and el is None:
                ok, why = False, "element does not exist"
            elif c.operation in {"create", "update"} and c.after is not None:
                if el is not None and el.realizes() and c.after.get("props", {}).get("realizes", el.realizes()) != el.realizes():
                    ok, why = False, "props.realizes is provenance-reserved"
                if not (c.after.get("props", {}).get(LINEAGE_KEY)):
                    ok, why = False, "semantic change without knowledge_lineage (Invariant 2)"
            results.append({"graph_id": c.graph_id, "element_id": c.element_id, "operation": c.operation, "ok": ok, "detail": why})
        return results

    def apply_change(self, changes):
        bad = [r for r in self.validate_change(changes) if not r["ok"]]
        if bad:
            raise GraphValidationError("; ".join(f"{b['element_id']}: {b['detail']}" for b in bad))
        for c in changes:
            g = self.graphs.setdefault(c.graph_id, {})
            if c.operation == "remove":
                g.pop(c.element_id, None)
                continue
            after = copy.deepcopy(c.after or {})
            after.pop("kind", None)                     # plan-05: the EOS node kind rides in `after`; GraphElement keeps its own `kind`
            el = g.get(c.element_id)
            if el is None:
                g[c.element_id] = GraphElement(graph_id=c.graph_id, element_id=c.element_id, kind=c.element_kind,
                                               scope=self._scope_of[c.graph_id], **after)
            else:
                data = el.model_dump()
                props = dict(data["props"])
                props.update(after.pop("props", {}))
                after.pop("source", None); after.pop("target", None)
                data.update(after)
                data["props"] = props
                g[c.element_id] = GraphElement(**data)
        self._save()

    def rollback_change(self, changes):
        for c in reversed(changes):
            g = self.graphs.setdefault(c.graph_id, {})
            if c.operation == "create":
                g.pop(c.element_id, None)
            elif c.before is not None:
                g[c.element_id] = GraphElement(graph_id=c.graph_id, element_id=c.element_id, kind=c.element_kind,
                                               scope=self._scope_of[c.graph_id], **c.before)
        self._save()

    def snapshot(self, graph_id: str, element_id: str) -> dict[str, Any] | None:
        el = self.get_graph_element(graph_id, element_id)
        return el.model_dump(include={"name", "description", "props", "source", "target"}) if el else None

    # plan-05 (block at the EOS adapter): the shadow store publishes by applying.
    def publish(self, scope, changes, *, actor, reason, base_version, rollback=False):
        if rollback:
            # `changes` is already the inverse list (graph_change.inverse_changes); apply it without the lineage gate,
            # because restoring a pre-KA element legitimately restores props that carried no lineage.
            for c in changes:
                g = self.graphs.setdefault(c.graph_id, {})
                if c.operation == "remove":
                    g.pop(c.element_id, None)
                elif c.after is not None:
                    data = dict(c.after); data.pop("kind", None); data.pop("source", None); data.pop("target", None)
                    el = g.get(c.element_id)
                    g[c.element_id] = GraphElement(graph_id=c.graph_id, element_id=c.element_id, kind=c.element_kind, scope=self._scope_of[c.graph_id],
                                                   source=el.source if el else None, target=el.target if el else None, **data)
            self._save()
            return PublishResult(applied=True, notes=["in-memory rollback"])
        bad = [r for r in self.validate_change(changes) if not r["ok"]]
        if bad:
            raise PublishRefused("invalid_change", "; ".join(f"{b['element_id']}: {b['detail']}" for b in bad), bad)
        self.apply_change(changes)
        return PublishResult(applied=True, pinned_instances=[s.scope_id for s in self.find_descendants(scope)] if scope.scope_type != ScopeType.INSTANCE else [])

    def base_version(self, scope):
        return None

    def resolve_element_id(self, scope, local_id):
        gid = self._graph_of.get(scope.key())
        if gid:
            for eid in self.graphs.get(gid, {}):
                if eid.endswith("/" + local_id):
                    return eid
        return local_id

    def edge_target_kind(self, edge):
        return {"contains": "process", "consumes": "entity", "produces": "entity", "acts_on": "entity", "performed_by": "actor",
                "governed_by": "rule", "emits": "event", "transitions_to": "state", "has_goal": "goal"}.get(edge)

    def needs_named_actor(self):
        return False


def _compare(parent: GraphElement, child: GraphElement) -> InheritanceState:
    ignore = {"realizes", LINEAGE_KEY}
    pp = {k: v for k, v in parent.props.items() if k not in ignore}
    cp = {k: v for k, v in child.props.items() if k not in ignore}
    if pp == cp and parent.name == child.name and parent.description == child.description:
        return InheritanceState.INHERITED
    # Extra keys only → extension; changed values → override.
    if all(cp.get(k) == v for k, v in pp.items()) and parent.name == child.name:
        return InheritanceState.LOCALLY_EXTENDED
    return InheritanceState.OVERRIDDEN


# ====================================================================== enterprise-os adapter


class EnterpriseOSGraphAdapter:
    """Thin wrapper over `knowledge_worker.graph_store.GraphStore`. Import is lazy so KA runs without the
    enterprise-os checkout; `available()` reports whether it can be used.

    Mapping: DOMAIN scope → substructure id; INSTANCE scope → instance id; element ids as in the store
    (`p.*`, `e.*`, `r.*`, edges `<kind>:<src>-><tgt>`). Domain writes create a NEW substructure version
    (the store has no in-place domain write); the operator repins instances via the store's `repin`.
    """

    KIND_MAP = {"process": GraphElementKind.PROCESS, "rule": GraphElementKind.RULE, "entity": GraphElementKind.CONCEPT,
                "state": GraphElementKind.NODE, "event": GraphElementKind.NODE, "attribute": GraphElementKind.NODE,
                "actor": GraphElementKind.NODE, "metric": GraphElementKind.COMPUTATION, "goal": GraphElementKind.NODE,
                "physical_source": GraphElementKind.COMPUTATION}

    def __init__(self, store: Any | None = None):
        self._store = store

    @staticmethod
    def available() -> bool:
        try:
            import knowledge_worker.graph_store  # noqa: F401
            return True
        except Exception:
            return False

    @property
    def store(self):
        if self._store is None:
            from knowledge_worker.graph_store import GraphStore  # type: ignore
            self._store = GraphStore()
        return self._store

    def graph_id_for(self, scope: Scope) -> str:
        return scope.scope_id

    def scope_for_graph(self, graph_id: str) -> Scope:
        if graph_id in self.store.list_instances():
            return Scope(scope_type=ScopeType.INSTANCE, scope_id=graph_id)
        return Scope(scope_type=ScopeType.DOMAIN, scope_id=graph_id)

    def _graph(self, graph_id: str):
        if graph_id in self.store.list_instances():
            _, g = self.store.get_instance(graph_id)
            return g
        return self.store.get_substructure(graph_id)

    def _wrap(self, graph_id: str, obj: Any, scope: Scope) -> GraphElement:
        if hasattr(obj, "source"):
            return GraphElement(graph_id=graph_id, element_id=obj.id, kind=GraphElementKind.EDGE, props=dict(obj.props),
                                scope=scope, source=obj.source, target=obj.target)
        return GraphElement(graph_id=graph_id, element_id=obj.id, kind=self.KIND_MAP.get(str(obj.kind), GraphElementKind.NODE),
                            name=obj.name, description=obj.description or "", props=dict(obj.props), scope=scope)

    def get_graph_element(self, graph_id, element_id):
        g = self._graph(graph_id)
        scope = self.scope_for_graph(graph_id)
        try:
            return self._wrap(graph_id, g.node(element_id), scope)
        except Exception:
            try:
                return self._wrap(graph_id, g.edge(element_id), scope)
            except Exception:
                return None

    def get_graph_lineage(self, graph_id, element_id):
        el = self.get_graph_element(graph_id, element_id)
        return el.lineage() if el else []

    def list_elements(self, scope):
        gid = self.graph_id_for(scope)
        g = self._graph(gid)
        return [self._wrap(gid, n, scope) for n in g.nodes] + [self._wrap(gid, e, scope) for e in g.edges]

    def find_elements_by_knowledge_nugget(self, nugget_id, version=None):
        out = []
        ids = list(self.store.list_substructures()) + list(self.store.list_instances())
        for gid in ids:
            for el in self.list_elements(self.scope_for_graph(gid)):
                if any(ln.get("nugget_id") == nugget_id and (version is None or ln.get("version") == version) for ln in el.lineage()):
                    out.append(el)
        return out

    def find_descendants(self, scope):
        if scope.scope_type == ScopeType.DOMAIN:
            return [Scope(scope_type=ScopeType.INSTANCE, scope_id=i) for i in self.store.pinned_by(scope.scope_id)]
        return []

    def calculate_inheritance(self, scope):
        states: dict[str, InheritanceState] = {}
        if scope.scope_type != ScopeType.INSTANCE:
            return states
        manifest, g = self.store.get_instance(scope.scope_id)
        for n in list(g.nodes) + list(g.edges):
            r = n.props.get("realizes")
            if not r:
                states[n.id] = InheritanceState.LOCALLY_EXTENDED
                continue
            try:
                parent_graph = self.store.get_substructure(r["substructure_id"], r.get("version"))
                pid = r.get("node_id") or r.get("edge_id")
                parent = parent_graph.node(pid) if r.get("node_id") else parent_graph.edge(pid)
            except Exception:
                states[n.id] = InheritanceState.CONFLICTING
                continue
            pp = {k: v for k, v in parent.props.items() if k not in {"realizes", LINEAGE_KEY, "lineage"}}
            cp = {k: v for k, v in n.props.items() if k not in {"realizes", LINEAGE_KEY, "lineage"}}
            same_name = getattr(parent, "name", None) == getattr(n, "name", None)
            if pp == cp and same_name:
                states[n.id] = InheritanceState.INHERITED
            elif all(cp.get(k) == v for k, v in pp.items()) and same_name:
                states[n.id] = InheritanceState.LOCALLY_EXTENDED
            else:
                states[n.id] = InheritanceState.OVERRIDDEN
        return states

    def validate_change(self, changes):
        results = []
        for c in changes:
            el = self.get_graph_element(c.graph_id, c.element_id)
            ok, why = True, "ok"
            if c.operation == "create" and el is not None:
                ok, why = False, "element already exists"
            elif c.operation != "create" and el is None:
                ok, why = False, "element does not exist"
            elif c.operation != "remove" and not (c.after or {}).get("props", {}).get(LINEAGE_KEY):
                ok, why = False, "semantic change without knowledge_lineage (Invariant 2)"
            elif el is not None and el.realizes() and (c.after or {}).get("props", {}).get("realizes", el.realizes()) != el.realizes():
                ok, why = False, "props.realizes is provenance-reserved"
            results.append({"graph_id": c.graph_id, "element_id": c.element_id, "operation": c.operation, "ok": ok, "detail": why})
        return results

    # [block plan-05]
    def apply_change(self, changes):
        raise NotImplementedError("EnterpriseOSGraphAdapter writes only through publish() — the EOS proposal lifecycle (plan-05, research-01 R1)")

    def rollback_change(self, changes):
        raise NotImplementedError("EnterpriseOSGraphAdapter rolls back only through publish(rollback=True) (plan-05)")

    def needs_named_actor(self):
        return True

    def base_version(self, scope):
        if scope.scope_type == ScopeType.DOMAIN:
            return self.store.list_substructures().get(scope.scope_id)
        return None

    def resolve_element_id(self, scope, local_id):
        if scope.scope_type == ScopeType.INSTANCE:
            manifest, g = self.store.get_instance(scope.scope_id)
            ids = {n.id for n in g.nodes} | {e.id for e in g.edges}
            for sid in manifest.pins:
                if f"{sid}/{local_id}" in ids:
                    return f"{sid}/{local_id}"
        return local_id

    def edge_target_kind(self, edge):
        try:
            from knowledge_worker.graph_model.edges import EDGE_SPECS  # type: ignore
            spec = EDGE_SPECS.get(edge)
            to = getattr(spec, "to", None) or getattr(spec, "to_kinds", None)
            return list(to)[0] if to else None
        except Exception:
            return {"contains": "process", "consumes": "entity", "produces": "entity", "acts_on": "entity", "performed_by": "actor",
                    "governed_by": "rule", "emits": "event", "transitions_to": "state"}.get(edge)

    def _typed_target(self, scope) -> bool:
        """Does the target graph pin a structure with a process-type table? Under `universal@1` `process_type` is an ERROR."""
        try:
            if scope.scope_type == ScopeType.INSTANCE:
                m, _ = self.store.get_instance(scope.scope_id)
                sid, ver = m.structure_id, m.structure_version
            else:
                g = self.store.get_substructure(scope.scope_id)
                sid, ver = g.structure_id, g.structure_version
            st = self.store.structures.get((sid, ver))
            return bool(st is not None and getattr(st, "process_type_table", None))
        except Exception:
            return False

    def publish(self, scope, changes, *, actor, reason, base_version, rollback=False):
        """Publish through EOS's own lifecycle: INSTANCE → propose_instance_change; DOMAIN → propose_promotion(base_version)
        → request_approval; then approve(actor) + apply unless HOTL already applied it. Never writes the store directly."""
        from knowledge_worker.graph_store import proposals as P  # type: ignore
        from knowledge_worker.graph_store.errors import GraphRejected, StoreError  # type: ignore
        from ka.graph_change import to_change_ops

        notes: list[str] = []
        ops = to_change_ops(changes)
        if not self._typed_target(scope):
            for op in ops:
                props = (op.get("node") or {}).get("props") if op.get("node") else op.get("props")
                if props and props.pop("process_type", None) is not None:
                    notes.append(f"process_type omitted on {op.get('id') or op['node']['id']}: target structure has no process-type table")
        for op in ops:
            props = (op.get("node") or op.get("edge") or {}).get("props") if (op.get("node") or op.get("edge")) else op.get("props")
            if props is not None:
                props.pop("description_text", None)
        try:
            if scope.scope_type == ScopeType.INSTANCE:
                pr = P.propose_instance_change(scope.scope_id, ops, actor=actor, reason=reason, store=self.store)
                if str(pr.status.value if hasattr(pr.status, "value") else pr.status) == "awaiting_approval":
                    pr = P.approve(pr.id, actor=actor, reason=reason, store=self.store)
                    pr = P.apply(pr.id, store=self.store)
                return PublishResult(applied=True, eos_proposal_id=pr.id, eos_status=str(getattr(pr.status, "value", pr.status)), notes=notes)
            if scope.scope_type != ScopeType.DOMAIN:
                raise PublishRefused("author_only", f"{scope.key()}: structure-tier publication is author-only in EOS")
            base = base_version or self.base_version(scope)
            pr = P.propose_promotion(scope.scope_id, base, ops=ops, actor=actor, reason=reason, store=self.store)
            pinned = list(getattr(pr.preview, "pinned_instances", []) or [])
            status = str(getattr(pr.status, "value", pr.status))
            if status == "previewed":
                pr = P.request_approval(pr.id, store=self.store)
                status = str(getattr(pr.status, "value", pr.status))
            if status == "awaiting_approval":
                pr = P.approve(pr.id, actor=actor, reason=reason, store=self.store)
                pr = P.apply(pr.id, store=self.store)
            return PublishResult(applied=True, eos_proposal_id=pr.id, eos_status=str(getattr(pr.status, "value", pr.status)),
                                 new_version=getattr(pr, "new_version", None), pinned_instances=pinned, notes=notes)
        except P.ProposalRefused as e:
            raise PublishRefused(getattr(e, "code", "refused"), str(e)) from e
        except GraphRejected as e:
            raise PublishRefused("graph_rejected", str(e), [f.model_dump() if hasattr(f, "model_dump") else str(f) for f in getattr(e, "findings", [])]) from e
        except StoreError as e:
            raise PublishRefused(type(e).__name__, str(e)) from e
    # [/block plan-05]
