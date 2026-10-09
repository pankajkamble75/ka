# [block plan-27]
"""Reconciliation (research-04 R6, §5): a submitted wiki draft becomes governance operations through the ONE pipeline. The block
diff's inserted and updated blocks go through the existing extractor (FEEDBACK channel, the page's scope, Q10's tiers); each extracted
statement is compared with the nuggets its block cites and with the page's selection, and classified; submission creates candidates
through `ingest_candidate`, revisions through `propose_revision`, retirement requests through `request_retirement` (Q18). Deleting prose
retires nothing. Nothing here edits an ACTIVE version, an article or a graph."""
from __future__ import annotations

import re
from typing import Any

from ka import config
from ka.conflict import similarity, subject_similarity
from ka.governance import CandidateInput, GovernanceError
from ka.model import Evidence, KnowledgeNuggetVersion, Scope, WikiDraft, WikiEditProposal
from ka.timeutil import now_iso
from ka.vocab import AcquisitionChannel, AuthorityType, SourceType
from ka.wiki import REF_MARK
from ka.wiki_markdown import block_diff

CLASSES = ("EDITORIAL_ONLY", "LINK_EXISTING", "ADD_CANDIDATE", "PROPOSE_REVISION", "PROPOSE_RETIREMENT", "NEEDS_EVIDENCE", "UNRESOLVED")
ABSOLUTE = re.compile(r"\d|\b(must|never|always|shall|required|prohibited)\b", re.I)
DELETE_NOTE = "deleting prose retires nothing; request retirement of the cited nugget explicitly (Q18)"


def _block_text(b: dict[str, Any]) -> str:
    parts = [b.get("text") or ""]
    for it in b.get("items", []) or []:
        parts.append(it["text"] + (f" [[{it['ref']}]]" if it.get("ref") else "") if isinstance(it, dict) else str(it))
    for row in b.get("rows", []) or []:
        parts.append(" ".join(row))
    return " ".join(p for p in parts if p).strip()


MARKS = re.compile(r"\*\*|\*|!\[[^\]]*\]\(image:\d+\)")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _plain(text: str) -> str:
    """The claim-bearing text: citations, bold/italic marks, images and link targets removed (they are editorial, not semantic)."""
    t = REF_MARK.sub("", text)
    t = LINK.sub(r"\1", t)
    t = MARKS.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


class _PlainClaim:
    """A sentence the extractor did not type: reviewed as a fact with low confidence."""

    def __init__(self, statement: str):
        from ka.vocab import KnowledgeType
        self.statement, self.title, self.knowledge_type, self.confidence = statement, statement[:60], KnowledgeType.FACT, 0.4


class Reconciler:
    def __init__(self, repo, governance, ingestion, wiki, extractor):
        self.repo, self.governance, self.ingestion, self.wiki, self.extractor = repo, governance, ingestion, wiki, extractor

    # ---- classification (preview; writes nothing) --------------------------------------------------------------------------

    def classify(self, draft: WikiDraft) -> dict[str, Any]:
        pg = self.wiki.page(draft.page_key)
        base = self.wiki.base_blocks(draft)
        diff = block_diff(base, draft.blocks)
        selection = self.wiki.select(draft.page_key)
        by_ref = {v.ref: v for v in selection}
        ops: list[dict[str, Any]] = []
        for d in diff:
            b = d["after"] or d["before"]
            if d["op"] == "delete":
                ops.append(self._op(d, "EDITORIAL_ONLY", statement=_plain(_block_text(b)), note=DELETE_NOTE, refs=b.get("refs", [])))
                continue
            if d["op"] == "move" or b.get("kind") == "heading":
                ops.append(self._op(d, "EDITORIAL_ONLY", statement=_plain(_block_text(b)), note="layout only"))
                continue
            text = _plain(_block_text(b))
            cited = [by_ref[r] for r in b.get("refs", []) if r in by_ref] + ([by_ref[r] for r in (d["before"] or {}).get("refs", []) if r in by_ref and d["before"]] if d["op"] == "update" else [])
            cited = list({v.ref: v for v in cited}.values())
            before_text = _plain(_block_text(d["before"])) if d["before"] else ""
            if d["op"] == "update" and _plain(text) == before_text:
                ops.append(self._op(d, "EDITORIAL_ONLY", statement=text, note="wording unchanged; formatting or citations only"))
                continue
            statements = self._statements(pg.title, b["id"], text)
            if not statements:
                cls = "UNRESOLVED" if len(text.split()) >= 6 else "EDITORIAL_ONLY"
                ops.append(self._op(d, cls, statement=text, note="nothing extractable for the reviewer to place" if cls == "UNRESOLVED" else "too short to carry a claim"))
                continue
            for st in statements:
                o = self._classify_statement(d, st, cited, selection, pg)
                o["refs"] = list(b.get("refs", []))                      # the block's citations travel with the operation (subject, provenance)
                ops.append(o)
            # a sentence the extractor did not recognise as a typed claim still goes to review as a plain fact — the editor wrote it on
            # purpose; it is never published without a decision (Q10: heuristic, untyped, pending review)
            covered = " ".join(st.statement for st in statements)
            for sent in re.split(r"(?<=[.!?])\s+", text):
                sent = sent.strip()
                if len(sent.split()) < 4 or similarity(sent, covered) >= 0.5 or any(similarity(sent, st.statement) >= 0.6 for st in statements):
                    continue
                if any(similarity(sent, v.statement) >= float(config.get("KA_DUPLICATE_THRESHOLD")) for v in cited):
                    continue
                st = _PlainClaim(sent)
                o = self._classify_statement(d, st, cited, selection, pg)
                o["refs"] = list(b.get("refs", []))
                if o["cls"] == "ADD_CANDIDATE":
                    o["note"] = "plain sentence; the extractor found no typed claim — reviewed as a fact"
                ops.append(o)
        for r in draft.requests or []:
            if r.get("kind") == "retire" and r.get("ref"):
                v = self.repo.version(r["ref"])
                ops.append({"block_id": None, "op": "request", "cls": "PROPOSE_RETIREMENT", "statement": v.statement if v else "", "target_ref": r["ref"],
                            "target_canonical": v.canonical_id if v else None, "note": r.get("why") or "", "by": r.get("by")})
        summary: dict[str, int] = {}
        for o in ops:
            summary[o["cls"]] = summary.get(o["cls"], 0) + 1
        return {"draft_id": draft.id, "page_key": draft.page_key, "diff": diff, "operations": ops, "summary": summary}

    def _op(self, d, cls, *, statement="", note="", target=None, refs=None, extra=None) -> dict[str, Any]:
        o = {"block_id": d["block_id"], "op": d["op"], "cls": cls, "statement": statement, "note": note, "target_ref": target.ref if target else None,
             "target_canonical": target.canonical_id if target else None, "refs": list(refs or [])}
        if extra:
            o.update(extra)
        return o

    def _statements(self, title: str, block_id: str, text: str):
        if not text:
            return []
        try:
            return self.extractor.extract(title=title, sections=[(block_id, text)], text=text)
        except Exception:  # noqa: BLE001 — a failed extraction is UNRESOLVED, never a crash
            return []

    def _classify_statement(self, d, st, cited: list[KnowledgeNuggetVersion], selection: list[KnowledgeNuggetVersion], pg) -> dict[str, Any]:
        dup_t = float(config.get("KA_DUPLICATE_THRESHOLD"))
        stmt = st.statement.strip()
        best, best_v = 0.0, None
        for v in cited:
            s = similarity(stmt, v.statement)
            if s > best:
                best, best_v = s, v
        if best_v is not None and (best >= dup_t or stmt.rstrip(".") == best_v.statement.rstrip(".")):
            return self._op(d, "LINK_EXISTING", statement=stmt, target=best_v, note=f"says what {best_v.ref} says (similarity {best:.2f})")
        # a changed claim revises the cited nugget it most resembles: subject overlap qualifies, raw similarity (numbers included) picks
        qualifying = [(similarity(stmt, v.statement), subject_similarity(stmt, v.statement), v) for v in cited]
        qualifying = [q for q in qualifying if q[1] >= 0.5]
        sub_v, sub_best = (None, 0.0)
        if qualifying:
            raw, sub_best, sub_v = max(qualifying, key=lambda q: (q[0], q[1]))
        if sub_v is not None:
            return self._op(d, "PROPOSE_REVISION", statement=stmt, target=sub_v, note=f"changes what {sub_v.ref} says (subject overlap {sub_best:.2f})",
                            extra={"knowledge_type": st.knowledge_type.value, "confidence": st.confidence})
        for v in selection:
            if similarity(stmt, v.statement) >= dup_t:
                return self._op(d, "LINK_EXISTING", statement=stmt, target=v, note=f"already governed as {v.ref}")
        scope = self._scope_for(pg, cited, selection)
        if not cited and pg.kind == "page" and ABSOLUTE.search(stmt) and pg.scope_type is None:
            return self._op(d, "NEEDS_EVIDENCE", statement=stmt, note="an absolute claim with no citation and no page scope; add a citation or a source")
        if scope is None:
            return self._op(d, "UNRESOLVED", statement=stmt, note="no scope: the page has none and the block cites nothing")
        return self._op(d, "ADD_CANDIDATE", statement=stmt, note="a new claim for review", extra={"knowledge_type": st.knowledge_type.value, "confidence": st.confidence,
                                                                                                  "scope": scope.key(), "title": st.title})

    def _scope_for(self, pg, cited, selection) -> Scope | None:
        if pg.scope_type and pg.scope_id:
            return Scope(scope_type=pg.scope_type, scope_id=pg.scope_id)
        if cited:
            return cited[0].scope
        if selection:
            return selection[0].scope
        return None

    # ---- submission (the one pipeline) -----------------------------------------------------------------------------------------

    def submit(self, draft: WikiDraft, *, by: str) -> WikiEditProposal:
        if draft.proposal_id and self.repo.wiki_proposals.get(draft.proposal_id):
            raise FileExistsError(f"draft {draft.id} already produced proposal {draft.proposal_id}")
        pg = self.wiki.page(draft.page_key)
        c = self.classify(draft)
        prop = WikiEditProposal(page_key=draft.page_key, draft_id=draft.id, diff=c["diff"], operations=c["operations"], submitted_by=by)
        producing = [o for o in c["operations"] if o["cls"] in ("ADD_CANDIDATE", "PROPOSE_REVISION", "PROPOSE_RETIREMENT")]
        src = ev_text = None
        if any(o["cls"] in ("ADD_CANDIDATE", "PROPOSE_REVISION") for o in producing):
            changed = [b for b in draft.blocks if any(o["block_id"] == b["id"] for o in producing)]
            ev_text = "\n\n".join(_plain(_block_text(b)) for b in changed) or draft.note or "wiki edit"
            scope = self._scope_for(pg, [], self.wiki.select(draft.page_key))
            got = self.ingestion.record_derived(title=f"Wiki draft {draft.id} — {pg.title}", text=ev_text, owner=by, scope=scope,
                                                channel=AcquisitionChannel.FEEDBACK, source_type=SourceType.NOTE, authority=AuthorityType.USER_KNOWLEDGE,
                                                visibility=pg.ceiling, metadata={"wiki_page": pg.key, "draft_id": draft.id})
            src = got.source
            src_version_id = got.version.id
        for o in producing:
            try:
                if o["cls"] == "PROPOSE_RETIREMENT":
                    rev = self.governance.request_retirement(o["target_canonical"], by=by, why=o.get("note") or "requested from the wiki")
                    o["produced_ref"] = rev.ref if rev is not None else None
                    if rev is None:
                        o["note"] = (o.get("note") or "") + " — already under review; nothing new created"
                    continue
                start = ev_text.find(o["statement"]) if ev_text else -1
                ev = self.repo.evidence.put(Evidence(source_id=src.id, source_version_id=src_version_id, locator=o["block_id"], excerpt=o["statement"][:600],
                                                     start=start if start >= 0 else None, end=start + len(o["statement"]) if start >= 0 else None,
                                                     created_by=by, visibility=pg.ceiling))
                if o["cls"] == "PROPOSE_REVISION":
                    prior = self.repo.require_version(o["target_ref"])
                    rev = self.governance.propose_revision(prior.canonical_id, statement=o["statement"], by=by, reason=f"wiki draft {draft.id}: {draft.note or 'edited paragraph'}",
                                                           source_ids=sorted(set(prior.source_refs) | {src.id}), evidence_ids=sorted(set(prior.evidence_refs) | {ev.id}),
                                                           subject=prior.subject, predicate=prior.predicate, object=prior.object)
                    o["produced_ref"] = rev.ref
                else:
                    scope_key = o.get("scope") or ""
                    st, _, sid = scope_key.partition(":")
                    from ka.vocab import ScopeType
                    scope = Scope(scope_type=ScopeType(st), scope_id=sid)
                    cited_subject = next((self.repo.version(r).subject for r in o.get("refs", []) if self.repo.version(r) and self.repo.version(r).subject), None)
                    cand = self.governance.ingest_candidate(CandidateInput(
                        title=(o.get("title") or o["statement"][:60]), statement=o["statement"], scope=scope, source_ids=[src.id], evidence_ids=[ev.id],
                        knowledge_type=o.get("knowledge_type", "fact"), authority_type=AuthorityType.USER_KNOWLEDGE, confidence=float(o.get("confidence") or 0.5),
                        channel=AcquisitionChannel.FEEDBACK, created_by=by, visibility=pg.ceiling, subject=cited_subject,
                        change_reason=f"wiki draft {draft.id}"))
                    o["produced_ref"] = cand.ref
            except GovernanceError as e:
                o["error"] = str(e)
        prop.operations = c["operations"]
        prop.produced_refs = [o["produced_ref"] for o in producing if o.get("produced_ref")]
        prop.updated_at = now_iso()
        self.repo.wiki_proposals.put(prop)
        draft.proposal_id = prop.id
        self.repo.wiki_drafts.put(draft)
        return prop
# [/block plan-27]
