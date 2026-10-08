# [block plan-04]
"""The second extraction pass (research-01 R3): read PROCESSES out of a document as assertions —
subject / predicate / object in EOS terms — on evidence that can be pointed at.

With a model: the prompt carries the CLOSED lists (EOS node kinds, KA predicates, the EOS process types, the slots) and
the rule "only when the text states it". Output outside the closed lists is dropped and disclosed in the extraction
report, never coerced (EOS grammar-first-navigation §2–§3). Without a model: a heuristic reads headings + numbered lists
into `description` / `decomposes_into` / `performed_by` and NEVER emits a type — a type the text does not state is
`not_evidenced`, which EOS later reports as an untyped process, not as a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ka.extraction import TextExtraction
from ka.grammar import GrammarRegistry
from ka.llm import LLMProvider, complete_json
from ka.vocab import PREDICATES

PROCESS_WORDS = re.compile(r"\b(process|procedure|workflow|handling|onboarding|underwriting|review|approval|settlement|"
                           r"reconciliation|dispute|fulfil+ment|intake|verification|collection|assessment)\b", re.I)
_LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[a-z][.)]|[-*•])\s+(.*\S)\s*$", re.I | re.M)
_PERFORMED = re.compile(r"(?:performed|carried out|handled|owned|run|executed)\s+by\s+(?:the\s+)?([A-Z][\w &/-]{2,60}?(?:\s(?:team|department|desk|unit|committee|group|function))?)\b"
                        r"|(?:the\s+)?([A-Z][\w &/-]{2,60}?(?:\s(?:team|department|desk|unit|committee|group)))\s+(?:is|are)\s+responsible\s+for", re.M)
_FIRST_SENTENCE = re.compile(r"^(.+?[.!?])(?:\s|$)", re.S)
_DASH = re.compile(r"\s+[—–-]{1,2}\s+|:\s+")


@dataclass
class AssertionCandidate:
    subject_kind: str
    subject_name: str
    predicate: str
    span_id: str
    locator: str
    excerpt: str
    confidence: float
    object_kind: str | None = None
    object_name: str | None = None
    object_value: str | None = None
    statement: str = ""


@dataclass
class ProcessExtraction:
    assertions: list[AssertionCandidate] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    method: str = "heuristic"


def render_statement(a: AssertionCandidate) -> str:
    s, o = a.subject_name, (a.object_name or a.object_value or "")
    return {
        "description": f"{s}: {o}",
        "typed_as": f"{s} is a {o} process.",
        "decomposes_into": f"{s} decomposes into: {o}",
        "consumes": f"{s} consumes: {o}",
        "produces": f"{s} produces: {o}",
        "acts_on": f"{s} acts on: {o}",
        "performed_by": f"{s} is performed by: {o}",
        "governed_by": f"{s} is governed by: {o}",
        "emits": f"{s} emits: {o}",
        "transitions_to": f"{s} transitions to: {o}",
        "precondition": f"{s} requires beforehand: {o}",
        "postcondition": f"{s} results in: {o}",
        "related_to": f"{s} relates to: {o}",
    }.get(a.predicate, f"{s} {a.predicate} {o}").strip()


_SYSTEM = ("You read enterprise documents and extract PROCESS knowledge as assertions for a governed knowledge system. "
           "Use ONLY the closed lists given. State ONLY what the text states; omit anything the text does not say. "
           "Never invent a process type, actor, input or output. Return ONLY a JSON array.")

_PROMPT = """PROCESS PASS — document: {title}
Section {locator} (span {span_id}):
\"\"\"
{text}
\"\"\"

Closed lists:
  subject/object kinds: {kinds}
  predicates: {predicates}
  process types (for typed_as ONLY when the text names the type): {types}
  slots (for reference): {slots}

Return a JSON array of objects: {{"subject_kind": "process", "subject_name": "...", "predicate": "...",
"object_kind": "process|entity|actor|rule|event|state|null", "object_name": "..." or null, "object_value": "..." or null,
"excerpt": "verbatim span of the text supporting it", "confidence": 0-1}}.
A numbered step under a process heading is `decomposes_into` with the step as a child process. A named team is `performed_by`.
"""


class ProcessExtractor:
    def __init__(self, provider: LLMProvider | None, grammar: GrammarRegistry | None):
        self.provider, self.grammar = provider, grammar

    # ---- entry -------------------------------------------------------------------------------------------

    def extract(self, title: str, extraction: TextExtraction) -> ProcessExtraction:
        if not extraction.sections:
            return ProcessExtraction()
        if self.provider is not None and getattr(self.provider, "name", "") != "stub":
            got = self._llm(title, extraction)
            if got.assertions or got.dropped:
                return got
        if self.provider is not None:
            got = self._llm(title, extraction)
            if got.assertions or got.dropped:
                return got
        return self._heuristic(extraction)

    # ---- model pass with closed lists ---------------------------------------------------------------------

    def _lists(self) -> dict[str, list[str]]:
        g = self.grammar
        return {"kinds": g.node_kinds() if g and g.loaded else ["process", "entity", "actor", "rule", "event", "state"],
                "predicates": list(PREDICATES), "types": g.type_names() if g and g.loaded else [],
                "slots": g.slots() if g and g.loaded else []}

    def _llm(self, title: str, extraction: TextExtraction) -> ProcessExtraction:
        out = ProcessExtraction(method="model")
        lists = self._lists()
        for sp in extraction.spans:
            text = extraction.text[sp.start:sp.end]
            items = complete_json(self.provider, _PROMPT.format(title=title, locator=sp.locator, span_id=sp.span_id, text=text[:6000],
                                                                 kinds=", ".join(lists["kinds"]), predicates=", ".join(lists["predicates"]),
                                                                 types=", ".join(lists["types"]) or "(none loaded)", slots=", ".join(lists["slots"])),
                                  system=_SYSTEM, default=[])
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    out.dropped.append({"item": it, "reason": "not an object", "span_id": sp.span_id})
                    continue
                pred, kind = str(it.get("predicate", "")), str(it.get("subject_kind", "process") or "process")
                if pred not in PREDICATES:
                    out.dropped.append({"item": it, "reason": f"predicate {pred!r} not in the closed list", "span_id": sp.span_id})
                    continue
                if kind not in lists["kinds"]:
                    out.dropped.append({"item": it, "reason": f"subject kind {kind!r} not an EOS node kind", "span_id": sp.span_id})
                    continue
                if not it.get("subject_name"):
                    out.dropped.append({"item": it, "reason": "no subject_name", "span_id": sp.span_id})
                    continue
                excerpt = str(it.get("excerpt") or "")
                if excerpt and excerpt not in text:
                    out.dropped.append({"item": {"excerpt": excerpt}, "reason": "excerpt not found in span; replaced by span text", "span_id": sp.span_id, "kept": True})
                    excerpt = text[:600]
                obj_kind = it.get("object_kind") or None
                if obj_kind and obj_kind not in lists["kinds"]:
                    obj_kind = None
                a = AssertionCandidate(subject_kind=kind, subject_name=str(it["subject_name"]).strip(), predicate=pred, span_id=sp.span_id,
                                       locator=sp.locator, excerpt=excerpt or text[:600], confidence=float(it.get("confidence", 0.6) or 0.6),
                                       object_kind=obj_kind, object_name=(str(it["object_name"]).strip() if it.get("object_name") else None),
                                       object_value=(str(it["object_value"]).strip() if it.get("object_value") else None))
                a.statement = render_statement(a)
                out.assertions.append(a)
        return out

    # ---- heuristic pass: headings + numbered lists ---------------------------------------------------------

    def _heuristic(self, extraction: TextExtraction) -> ProcessExtraction:
        out = ProcessExtraction(method="heuristic")
        for sp in extraction.spans:
            heading = sp.locator if not sp.locator.startswith(("¶", "p.", "slide", "table", "sheet")) else ""
            text = extraction.text[sp.start:sp.end]
            items = [m.group(1).strip() for m in _LIST_ITEM.finditer(text)]
            if not heading or not (PROCESS_WORDS.search(heading) or len(items) >= 2):
                continue
            body = _LIST_ITEM.sub("", text).strip()
            first = _FIRST_SENTENCE.match(" ".join(body.split()))
            if first:
                sentence = first.group(1).strip()
                a = AssertionCandidate("process", heading, "description", sp.span_id, sp.locator, sentence, 0.7, object_value=sentence)
                a.statement = render_statement(a)
                out.assertions.append(a)
            m = _PERFORMED.search(text)
            if m:
                actor = (m.group(1) or m.group(2) or "").strip()
                if actor:
                    a = AssertionCandidate("process", heading, "performed_by", sp.span_id, sp.locator, m.group(0).strip(), 0.7,
                                           object_kind="actor", object_name=actor)
                    a.statement = render_statement(a)
                    out.assertions.append(a)
            for item in items:
                child = _DASH.split(item, maxsplit=1)[0].strip().rstrip(".")[:60]
                if len(child) < 3:
                    continue
                a = AssertionCandidate("process", heading, "decomposes_into", sp.span_id, sp.locator, item, 0.75, object_kind="process", object_name=child)
                a.statement = render_statement(a)
                out.assertions.append(a)
        return out
# [/block plan-04]
