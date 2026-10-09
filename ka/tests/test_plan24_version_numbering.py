"""plan-24 (research-03 R15) — version numbers derived from the versions on disk and the counter written first: a lost source write never
yields a duplicate (source, version); the repair tool renumbers an existing duplicate without touching version ids."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ka.extraction import source_type_for_filename
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition
from ka.tests.conftest import D, P, S
from ka.vocab import AuthorityType, Visibility

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.backfill_physical import repair_conflicts  # noqa: E402

A, B, C = b"Policy text one.\n", b"Policy text two.\n", b"Policy text three.\n"


@pytest.fixture
def ka(tmp_path):
    k = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider(), auto_approve_low_impact=False)
    for s_, p_ in [(S, None), (P, S), (D, P)]:
        k.register_scope(s_, p_)
    return k


def _ing(ka, data):
    """The same located source each time (uploads never match an existing source; a located ingest does)."""
    return ka.ingestion._ingest(title="p", data=data, source_type=source_type_for_filename("p.md"), owner="ops", scope=D,
                                authority=AuthorityType.PROJECT_DOCUMENTATION, visibility=Visibility.ENTERPRISE, filename="p.md", location="file:///p.md")


def _roll_back_counter(ka, src_id, to):
    """Simulate the lost write: the Source file on disk still carries the OLD counter (and the repository cache follows it)."""
    path = ka.repo.root / "sources" / f"{src_id}.json"
    d = json.loads(path.read_text()); d["content_version"] = to; path.write_text(json.dumps(d))
    ka.repo.sources._cache = None
    ka.repo.source_versions._cache = None


def test_P1_changed_bytes_number_v2_then_v3_and_the_counter_follows(ka):
    g1 = _ing(ka, A)
    g2 = _ing(ka, B)
    g3 = _ing(ka, C)
    assert (g1.version.version, g2.version.version, g3.version.version) == (1, 2, 3) and g1.source.id == g3.source.id
    assert ka.repo.sources.require(g1.source.id).content_version == 3


def test_P2_a_lost_counter_write_never_yields_a_duplicate_on_ingest(ka):
    g1 = _ing(ka, A)
    _ing(ka, B)
    _roll_back_counter(ka, g1.source.id, to=1)                        # disk says v1 although v2 exists
    g3 = _ing(ka, C)
    nums = sorted(v.version for v in ka.repo.source_versions.where(lambda v: v.source_id == g1.source.id))
    assert nums == [1, 2, 3] and g3.version.version == 3 and len(set(nums)) == 3
    assert ka.repo.binding_for_version(g3.version.id).ka_source_version == 3 and ka.repo.sources.require(g1.source.id).content_version == 3


def test_P3_a_lost_counter_write_never_yields_a_duplicate_on_reextract(ka):
    g1 = _ing(ka, A)
    g2 = ka.ingestion.reextract(g1.source.id, owner="ops")
    assert g2.version.version == 2
    _roll_back_counter(ka, g1.source.id, to=1)
    g3 = ka.ingestion.reextract(g1.source.id, owner="ops")
    nums = sorted(v.version for v in ka.repo.source_versions.where(lambda v: v.source_id == g1.source.id))
    assert nums == [1, 2, 3] and g3.version.version == 3


def test_P4_repair_renumbers_the_later_duplicate_and_a_backfill_then_reports_no_conflict(ka):
    g1 = _ing(ka, A)
    g2 = _ing(ka, B)
    dup = ka.repo.source_versions.require(g2.version.id)
    dup.version = 1                                                   # forge the live anomaly: two v1 with different bytes
    ka.repo.source_versions.put(dup)
    ids_before = sorted(v.id for v in ka.repo.source_versions.all())
    dry = repair_conflicts(ka, apply=False)
    assert dry["duplicate_keys"] == 1 and dry["would_renumber"] == 1 and dry["renumbered"] == [] and ka.repo.source_versions.require(dup.id).version == 1
    rep = repair_conflicts(ka, apply=True)
    assert rep["renumbered"] == [{"source": g1.source.id, "source_version_id": dup.id, "from": 1, "to": 2}]
    assert ka.repo.source_versions.require(dup.id).version == 2 and ka.repo.source_versions.require(g1.version.id).version == 1    # earliest keeps 1
    assert ka.repo.binding_for_version(dup.id).ka_source_version == 2 and ka.repo.sources.require(g1.source.id).content_version == 2
    assert sorted(v.id for v in ka.repo.source_versions.all()) == ids_before
    assert repair_conflicts(ka, apply=False)["duplicate_keys"] == 0


def test_N1_repair_never_touches_a_source_whose_numbers_are_unique(ka):
    _ing(ka, A)
    _ing(ka, B)
    files = {p: p.read_bytes() for p in (ka.repo.root / "source_versions").glob("*.json")} | {p: p.read_bytes() for p in (ka.repo.root / "sources").glob("*.json")}
    rep = repair_conflicts(ka, apply=True)
    assert rep["duplicate_keys"] == 0 and rep["renumbered"] == []
    assert all(p.read_bytes() == b for p, b in files.items())


def test_N2_a_gap_after_a_counter_only_write_is_numbered_past_and_nothing_raises(ka):
    g1 = _ing(ka, A)
    src = ka.repo.sources.require(g1.source.id)
    src.content_version = 7                                           # the counter advanced; no v2..v7 exist (a stop before the version write)
    ka.repo.sources.put(src)
    g2 = _ing(ka, B)
    assert g2.version.version == 8 and sorted(v.version for v in ka.repo.source_versions.where(lambda v: v.source_id == src.id)) == [1, 8]


def test_N3_plan04_and_plan18_tests_are_unmodified():
    root = Path(__file__).resolve().parents[2]
    for f in ("ka/tests/test_plan04_process_extraction.py", "ka/tests/test_plan18_physical_store.py"):
        assert subprocess.run(["git", "diff", "--quiet", "HEAD", "--", f], cwd=root).returncode == 0, f"{f} differs from HEAD"
