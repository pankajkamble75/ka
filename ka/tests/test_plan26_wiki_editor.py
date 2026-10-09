"""plan-26 (research-04 R5; product tests PT3 half, PT9) — the wiki editor: a Markdown subset parsed into blocks (no HTML ever), drafts with
an optimistic lock, block diff by stable id, submission refused while another draft is under review, authored pages; editing changes no
nugget, no article, no graph."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka
from ka.tests.conftest import D
from ka.tests.test_plan25_wiki_read import _subject_nuggets
from ka.vocab import Visibility
from ka.wiki import DraftConflict, StaleDraft
from ka.wiki_markdown import MarkdownRefused, block_diff, parse, to_markdown

ROOT = Path(__file__).resolve().parents[2]
KEY = "subject:refund_policy"
SAMPLE = """<!-- b1 -->
# Refund handbook

<!-- b2 -->
Refunds above $900 need **manager** approval. [[KN-001:v1]] See [policy](https://example.com/p).

- first item [[KN-002:v1]]
- second *item*

1. step one
2. step two

> a quoted line [[KN-003:v1]]

| Amount | Approver |
|---|---|
| $900 | Manager |

![diagram](image:12)
"""


def _tree(ka):
    return {p: p.read_bytes() for d in ("nuggets", "proposals") for p in (ka.repo.root / d).glob("*.json")}


def test_P1_parse_covers_the_grammar_and_round_trips_with_ids():
    bs = parse(SAMPLE)
    assert [b["kind"] for b in bs] == ["heading", "paragraph", "list", "list", "quote", "table", "paragraph"]
    assert bs[0]["id"] == "b1" and bs[1]["id"] == "b2" and bs[2]["id"].startswith("n")
    assert bs[1]["refs"] == ["KN-001:v1"] and bs[2]["refs"] == ["KN-002:v1"] and bs[4]["refs"] == ["KN-003:v1"]
    assert bs[2]["ordered"] is False and bs[3]["ordered"] is True and bs[5]["rows"] == [["Amount", "Approver"], ["$900", "Manager"]]
    rt = parse(to_markdown(bs))
    assert [(b["kind"], b.get("text"), b.get("items"), b.get("rows")) for b in rt] == [(b["kind"], b.get("text"), b.get("items"), b.get("rows")) for b in bs]
    assert [b["id"] for b in rt] == [b["id"] for b in bs]


def test_P2_start_draft_copies_the_article_or_the_layout(ka):
    _subject_nuggets(ka, 3)
    d = ka.wiki.start_draft(KEY, by="editor")
    art = ka.wiki.article(KEY)
    assert [b["id"] for b in d.blocks] == [b["id"] for b in art["blocks"]] and d.base_digest == art["digest"] and d.state == "DRAFT" and d.rev == 0
    pg, d2 = ka.wiki.create_page(slug="refund-handbook", title="Refund handbook", scope=D, ceiling=Visibility.ENTERPRISE, by="editor")
    assert pg.key == "page:refund-handbook" and d2.blocks == pg.layout["blocks"] and d2.page_key == pg.key


def test_P3_save_bumps_the_rev_and_preview_writes_nothing(ka):
    _subject_nuggets(ka, 2)
    d = ka.wiki.start_draft(KEY, by="editor")
    md = ka.wiki.draft_markdown(d).replace("level 0.", "level ZERO.")
    d2 = ka.wiki.save_draft(d.id, text=md, expected_rev=0, by="editor")
    assert d2.rev == 1 and any("ZERO" in b["text"] for b in d2.blocks) and [b["id"] for b in d2.blocks] == [b["id"] for b in d.blocks]
    before = (ka.repo.root / "wiki_drafts" / f"{d.id}.json").read_bytes()
    assert ka.wiki.preview("# only a preview\n\nnew text")[1]["text"] == "new text"
    assert (ka.repo.root / "wiki_drafts" / f"{d.id}.json").read_bytes() == before


def test_P4_block_diff_names_update_insert_delete_and_move():
    old = parse(SAMPLE)
    new = [dict(b) for b in old]
    new[1] = dict(new[1], text="Refunds above $950 need approval. [[KN-001:v1]]")
    del new[4]
    new.append({"id": "n9", "kind": "paragraph", "text": "New para.", "level": 2, "refs": []})
    ops = {d["block_id"]: d["op"] for d in block_diff(old, new)}
    assert ops["b2"] == "update" and ops[old[4]["id"]] == "delete" and ops["n9"] == "insert" and "b1" not in ops
    swapped = [old[0], old[2], old[1]] + old[3:]
    assert {d["op"] for d in block_diff(old, swapped)} == {"move"}


def test_P5_submit_records_the_diff_and_emits_close_closes(ka):
    _subject_nuggets(ka, 2)
    d = ka.wiki.start_draft(KEY, by="editor")
    ka.wiki.save_draft(d.id, text=ka.wiki.draft_markdown(d) + "\nA brand new paragraph.\n", expected_rev=0, by="editor")
    s = ka.wiki.submit_draft(d.id, by="editor", note="please review")
    assert s.state == "SUBMITTED" and s.note == "please review"
    assert [x["op"] for x in ka.wiki.diff(d.id)["diff"]] == ["insert"]
    assert any(e["name"] == "wiki.draft.submitted" for e in ka.repo.events())
    assert ka.wiki.close_draft(d.id, by="editor").state == "CLOSED"


def test_P6_an_authored_page_renders_its_blocks_and_is_listed(ka):
    vs = _subject_nuggets(ka, 1)
    pg, d = ka.wiki.create_page(slug="handbook", title="Handbook", scope=D, ceiling=Visibility.ENTERPRISE, by="editor")
    ka.wiki.save_draft(d.id, text=f"<!-- n1 -->\n# Handbook\n\nOur rule: see [[{vs[0].ref}]].\n\n- a point\n", expected_rev=0, by="editor")
    pg.layout["blocks"] = ka.repo.wiki_drafts.require(d.id).blocks          # plan-28 applies layouts; here the test does it
    ka.repo.wiki_pages.put(pg)
    a = ka.wiki.article("page:handbook")
    assert a["kind"] == "page" and [b["origin"] for b in a["blocks"]] == ["authored"] * 3 and a["refs"] == [vs[0].ref]
    assert any(p["key"] == "page:handbook" for p in ka.wiki.list_pages()["pages"])


def test_P7_routes_and_flow(ka):
    _subject_nuggets(ka, 2)
    c = TestClient(create_app(ka))
    r = c.post(f"{PREFIX}/wiki/pages/{KEY}/drafts", json={"by": "editor"}).json()
    did = r["draft"]["id"]
    assert "<!-- b" in r["markdown"]
    s = c.put(f"{PREFIX}/wiki/drafts/{did}", json={"text": r["markdown"] + "\nMore.\n", "expected_rev": 0, "by": "editor"}).json()
    assert s["draft"]["rev"] == 1
    assert c.post(f"{PREFIX}/wiki/drafts/{did}/preview", json={"text": "# x\n\ny"}).json()["blocks"][1]["text"] == "y"
    assert c.get(f"{PREFIX}/wiki/drafts/{did}/diff").json()["diff"][0]["op"] == "insert"
    assert c.get(f"{PREFIX}/wiki/pages/{KEY}/drafts").json()["drafts"][0]["id"] == did
    assert c.post(f"{PREFIX}/wiki/drafts/{did}/submit", json={"by": "editor"}).json()["draft"]["state"] == "SUBMITTED"
    pg = c.post(f"{PREFIX}/wiki/pages", json={"slug": "notes", "title": "Notes", "by": "editor"}).json()
    assert pg["page"]["key"] == "page:notes" and pg["draft"]["page_key"] == "page:notes"
    set_ka(None)
    assert (ROOT / "e2e" / "plan26_wiki_editor_flow.py").exists()


def test_N1_PT9a_a_stale_expected_rev_is_refused_and_the_draft_is_unchanged(ka):
    _subject_nuggets(ka, 2)
    d = ka.wiki.start_draft(KEY, by="a")
    ka.wiki.save_draft(d.id, text=ka.wiki.draft_markdown(d) + "\nA.\n", expected_rev=0, by="a")
    with pytest.raises(StaleDraft) as e:
        ka.wiki.save_draft(d.id, text=ka.wiki.draft_markdown(d) + "\nB.\n", expected_rev=0, by="b")
    assert e.value.rev == 1 and ka.repo.wiki_drafts.require(d.id).rev == 1 and not any("B." == b["text"] for b in ka.repo.wiki_drafts.require(d.id).blocks)
    c = TestClient(create_app(ka))
    r = c.put(f"{PREFIX}/wiki/drafts/{d.id}", json={"text": "x", "expected_rev": 0, "by": "b"})
    assert r.status_code == 409 and r.json()["detail"]["rev"] == 1
    set_ka(None)


def test_N2_PT9b_a_second_draft_saves_but_cannot_be_submitted_while_the_first_is_under_review(ka):
    _subject_nuggets(ka, 2)
    d1 = ka.wiki.start_draft(KEY, by="a"); d2 = ka.wiki.start_draft(KEY, by="b")
    ka.wiki.save_draft(d2.id, text=ka.wiki.draft_markdown(d2) + "\nB.\n", expected_rev=0, by="b")
    ka.wiki.submit_draft(d1.id, by="a")
    with pytest.raises(DraftConflict, match=d1.id):
        ka.wiki.submit_draft(d2.id, by="b")
    assert ka.repo.wiki_drafts.require(d2.id).state == "DRAFT"
    ka.wiki.close_draft(d1.id, by="a")
    assert ka.wiki.submit_draft(d2.id, by="b").state == "SUBMITTED"


@pytest.mark.parametrize("bad", ["<script>alert(1)</script>", "x <img src=x onerror=alert(1)>", "[a](javascript:alert(1))", "![x](data:image/png;base64,AAAA)", "<!-- not an id -->", "[a](ftp://x)"])
def test_N3_html_and_unsafe_links_are_refused_naming_the_line(ka, bad):
    _subject_nuggets(ka, 1)
    d = ka.wiki.start_draft(KEY, by="a")
    with pytest.raises(MarkdownRefused) as e:
        ka.wiki.save_draft(d.id, text="# t\n\n" + bad + "\n", expected_rev=0, by="a")
    assert e.value.line_no == 3 and ka.repo.wiki_drafts.require(d.id).rev == 0
    c = TestClient(create_app(ka))
    r = c.put(f"{PREFIX}/wiki/drafts/{d.id}", json={"text": "# t\n\n" + bad + "\n", "expected_rev": 0, "by": "a"})
    assert r.status_code == 400 and r.json()["detail"]["line"] == 3
    set_ka(None)


def test_N4_PT3_half_editing_changes_no_nugget_article_or_proposal(ka):
    _subject_nuggets(ka, 3)
    before, art0 = _tree(ka), ka.wiki.article(KEY)["blocks"]
    d = ka.wiki.start_draft(KEY, by="a")
    ka.wiki.save_draft(d.id, text=ka.wiki.draft_markdown(d).replace("level 0.", "level 99.") + "\nInvented activity: approve by phone.\n", expected_rev=0, by="a")
    ka.wiki.submit_draft(d.id, by="a")
    now = _tree(ka)
    assert all(now[p] == b for p, b in before.items()) and ka.wiki.article(KEY)["blocks"] == art0   # existing versions, proposals and the article untouched
    assert len(ka.repo.proposals.all()) == len([p for p in before if "proposals" in str(p)])         # no graph proposal
    # plan-27: submission MAY add new candidate files (PENDING_REVIEW) — that is the point of PT3; nothing governed moved


def test_N5_unknown_key_bad_slug_and_missing_by(ka):
    c = TestClient(create_app(ka))
    assert c.post(f"{PREFIX}/wiki/pages/subject:nobody/drafts", json={"by": "a"}).status_code == 404
    assert c.post(f"{PREFIX}/wiki/pages", json={"slug": "Bad Slug!", "title": "x", "by": "a"}).status_code == 400
    assert c.post(f"{PREFIX}/wiki/pages", json={"slug": "ok-slug", "title": "x", "by": "a"}).status_code == 200
    assert c.post(f"{PREFIX}/wiki/pages", json={"slug": "ok-slug", "title": "x", "by": "a"}).status_code == 409
    assert c.post(f"{PREFIX}/wiki/pages", json={"slug": "other", "title": "x"}).status_code == 422
    set_ka(None)


def test_N6_stored_block_text_never_contains_html(ka):
    _subject_nuggets(ka, 2)
    d = ka.wiki.start_draft(KEY, by="a")
    ka.wiki.save_draft(d.id, text=SAMPLE, expected_rev=0, by="a")
    for b in ka.repo.wiki_drafts.require(d.id).blocks:
        assert "<" not in b.get("text", "") and all("<" not in str(i) for i in b.get("items", [])) and all("<" not in c for r in b.get("rows", []) for c in r)
