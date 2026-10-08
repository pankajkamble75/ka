"""plan-01 — §39 adapter over the real enterprise-os GraphStore. READ-ONLY, and skipped unless the checkout
and its storage are reachable (KA_ENTERPRISE_OS_ROOT / KW_STORAGE_ROOT, or the sibling checkout)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ka.model import Scope
from ka.vocab import InheritanceState, ScopeType

_ROOT = os.environ.get("KA_ENTERPRISE_OS_ROOT") or "/root/enterprise-os-070626"
_STORAGE = os.environ.get("KW_STORAGE_ROOT") or "/root/enterprise-os-dev-data/storage"


def _adapter():
    if not (Path(_ROOT, "knowledge_worker").exists() and Path(_STORAGE, "graph_v2").exists()):
        pytest.skip("enterprise-os checkout or storage not reachable")
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    os.environ.setdefault("KW_STORAGE_ROOT", _STORAGE)
    from ka.graph_adapter import EnterpriseOSGraphAdapter
    if not EnterpriseOSGraphAdapter.available():
        pytest.skip("knowledge_worker.graph_store not importable from this interpreter")
    return EnterpriseOSGraphAdapter()


def test_P1_domains_instances_and_elements_are_readable():
    a = _adapter()
    domains = a.store.list_substructures()
    assert domains
    sid = sorted(domains)[0]
    els = a.list_elements(Scope(scope_type=ScopeType.DOMAIN, scope_id=sid))
    assert els and all(e.graph_id == sid for e in els)
    el = a.get_graph_element(sid, els[0].element_id)
    assert el is not None and el.element_id == els[0].element_id


def test_P2_inheritance_states_are_derived_from_realizes():
    a = _adapter()
    for sid in sorted(a.store.list_substructures()):
        kids = a.find_descendants(Scope(scope_type=ScopeType.DOMAIN, scope_id=sid))
        if kids:
            states = a.calculate_inheritance(kids[0])
            assert states and set(states.values()) <= set(InheritanceState)
            assert InheritanceState.INHERITED in states.values()
            return
    pytest.skip("no instance pinned to any domain")


def test_N1_a_change_without_lineage_is_refused_before_touching_the_store():
    from ka.model import ElementChange
    from ka.vocab import GraphElementKind
    a = _adapter()
    sid = sorted(a.store.list_substructures())[0]
    bad = ElementChange(graph_id=sid, element_id="r.ka_test_rogue", element_kind=GraphElementKind.RULE, operation="create",
                        after={"name": "rogue", "props": {}})
    res = a.validate_change([bad])
    assert res[0]["ok"] is False and "Invariant 2" in res[0]["detail"]
