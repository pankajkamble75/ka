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


class GraphValidationError(RuntimeError):
    pass


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
            el = g.get(c.element_id)
            if el is None:
                g[c.element_id] = GraphElement(graph_id=c.graph_id, element_id=c.element_id, kind=c.element_kind,
                                               scope=self._scope_of[c.graph_id], **after)
            else:
                data = el.model_dump()
                props = dict(data["props"])
                props.update(after.pop("props", {}))
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

    def apply_change(self, changes):
        from knowledge_worker.graph_model.model import Edge, Node  # type: ignore

        bad = [r for r in self.validate_change(changes) if not r["ok"]]
        if bad:
            raise GraphValidationError("; ".join(f"{b['element_id']}: {b['detail']}" for b in bad))
        by_graph: dict[str, list[ElementChange]] = {}
        for c in changes:
            by_graph.setdefault(c.graph_id, []).append(c)
        for gid, cs in by_graph.items():
            is_instance = gid in self.store.list_instances()
            g = self._graph(gid)
            nodes = {n.id: n for n in g.nodes}
            edges = {e.id: e for e in g.edges}
            for c in cs:
                after = dict(c.after or {})
                props_patch = after.pop("props", {})
                if c.operation == "remove":
                    nodes.pop(c.element_id, None)
                    edges.pop(c.element_id, None)
                    continue
                if c.element_kind == GraphElementKind.EDGE:
                    cur = edges.get(c.element_id)
                    data = cur.model_dump() if cur else {"id": c.element_id, "kind": after.get("kind", "relates_to"),
                                                          "source": after.get("source"), "target": after.get("target"), "props": {}}
                    data["props"] = {**data["props"], **props_patch}
                    edges[c.element_id] = Edge(**data)
                else:
                    cur = nodes.get(c.element_id)
                    data = cur.model_dump() if cur else {"id": c.element_id, "kind": after.get("kind", "rule"), "name": after.get("name", c.element_id),
                                                          "description": after.get("description", ""), "props": {}}
                    for k in ("name", "description"):
                        if k in after:
                            data[k] = after[k]
                    data["props"] = {**data["props"], **props_patch}
                    nodes[c.element_id] = Node(**data)
            new_graph = g.model_copy(update={"nodes": list(nodes.values()), "edges": list(edges.values())})
            if is_instance:
                self.store.put_instance_graph(gid, new_graph)
            else:
                self.store.put_substructure(new_graph)   # new immutable domain version; instances repin separately

    def rollback_change(self, changes):
        inverse = []
        for c in reversed(changes):
            if c.operation == "create":
                inverse.append(ElementChange(graph_id=c.graph_id, element_id=c.element_id, element_kind=c.element_kind, operation="remove"))
            elif c.before is not None:
                inverse.append(ElementChange(graph_id=c.graph_id, element_id=c.element_id, element_kind=c.element_kind,
                                             operation="update", after=c.before))
        # rollback writes go straight through; the lineage they restore is the pre-change lineage
        from knowledge_worker.graph_model.model import Edge, Node  # type: ignore  # noqa: F401
        self._apply_unvalidated(inverse)

    def _apply_unvalidated(self, changes):
        saved = self.validate_change
        self.validate_change = lambda cs: [{"ok": True}]  # type: ignore
        try:
            self.apply_change(changes)
        finally:
            self.validate_change = saved  # type: ignore
