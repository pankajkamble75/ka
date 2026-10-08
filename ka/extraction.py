"""knowledge-extraction (§4, §11): raw bytes → text, and text → candidate Knowledge Nuggets.

Two layers, deliberately separate:
  * `extract_text` turns a file / URL / note into text. Optional libraries (pypdf, python-docx,
    python-pptx, openpyxl, beautifulsoup4) are imported lazily; without them the source is stored with
    extraction_status UNAVAILABLE rather than refused — raw content is evidence either way (§4.1).
  * `CandidateExtractor` turns text into candidate statements. With an LLM it asks for discrete,
    independently governable statements (§5: one document → many nuggets); without one, a heuristic
    sentence splitter keeps the pipeline runnable and testable.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ka.llm import LLMProvider, complete_json
from ka.vocab import ExtractionStatus, KnowledgeType, SourceType

MEDIA_TYPES = {
    SourceType.PDF: "application/pdf",
    SourceType.WORD: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    SourceType.POWERPOINT: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    SourceType.SPREADSHEET: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    SourceType.MARKDOWN: "text/markdown",
    SourceType.IMAGE: "image/*",
}

_EXT_TO_TYPE = {
    ".pdf": SourceType.PDF, ".docx": SourceType.WORD, ".pptx": SourceType.POWERPOINT,
    ".xlsx": SourceType.SPREADSHEET, ".xlsm": SourceType.SPREADSHEET, ".csv": SourceType.SPREADSHEET,
    ".md": SourceType.MARKDOWN, ".markdown": SourceType.MARKDOWN, ".txt": SourceType.TEXT,
    ".png": SourceType.IMAGE, ".jpg": SourceType.IMAGE, ".jpeg": SourceType.IMAGE, ".gif": SourceType.IMAGE,
    ".html": SourceType.URL, ".htm": SourceType.URL,
}


def source_type_for_filename(name: str) -> SourceType:
    name = name.lower()
    for ext, t in _EXT_TO_TYPE.items():
        if name.endswith(ext):
            return t
    return SourceType.COMPANY_DOCUMENT


@dataclass
class TextExtraction:
    text: str
    status: ExtractionStatus
    note: str | None = None
    media_type: str = "text/plain"
    sections: list[tuple[str, str]] = field(default_factory=list)   # (locator, text) for evidence locators


def extract_text(data: bytes, source_type: SourceType, filename: str | None = None) -> TextExtraction:
    try:
        if source_type in {SourceType.TEXT, SourceType.NOTE, SourceType.MANUAL, SourceType.MARKDOWN,
                           SourceType.CORRECTION, SourceType.RESEARCH, SourceType.COMPANY_DOCUMENT, SourceType.GITHUB}:
            text = data.decode("utf-8", errors="replace")
            return TextExtraction(text, ExtractionStatus.EXTRACTED, media_type=MEDIA_TYPES.get(source_type, "text/plain"),
                                  sections=_markdown_sections(text) if source_type == SourceType.MARKDOWN else _paragraphs(text))
        if source_type == SourceType.PDF:
            return _pdf(data)
        if source_type == SourceType.WORD:
            return _docx(data)
        if source_type == SourceType.POWERPOINT:
            return _pptx(data)
        if source_type == SourceType.SPREADSHEET:
            return _xlsx(data, filename)
        if source_type == SourceType.URL:
            return _html(data)
        if source_type == SourceType.IMAGE:
            return TextExtraction("", ExtractionStatus.UNAVAILABLE, "image extraction not configured", "image/*")
        if source_type == SourceType.CONNECTOR:
            text = data.decode("utf-8", errors="replace")
            return TextExtraction(text, ExtractionStatus.EXTRACTED, sections=_paragraphs(text))
    except ImportError as e:
        return TextExtraction("", ExtractionStatus.UNAVAILABLE, f"extractor library missing: {e.name}")
    except Exception as e:  # noqa: BLE001 — a broken file must not break ingestion
        return TextExtraction("", ExtractionStatus.FAILED, f"{type(e).__name__}: {e}")
    return TextExtraction("", ExtractionStatus.UNAVAILABLE, f"no extractor for {source_type.value}")


def _paragraphs(text: str) -> list[tuple[str, str]]:
    out, n = [], 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if para:
            n += 1
            out.append((f"¶{n}", para))
    return out


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    out, heading, buf = [], "preamble", []
    for line in text.splitlines():
        if line.startswith("#"):
            if buf:
                out.append((heading, "\n".join(buf).strip()))
            heading, buf = line.lstrip("#").strip() or heading, []
        else:
            buf.append(line)
    if buf:
        out.append((heading, "\n".join(buf).strip()))
    return [(h, t) for h, t in out if t]


def _pdf(data: bytes) -> TextExtraction:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    sections = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            sections.append((f"p.{i}", t))
    text = "\n\n".join(t for _, t in sections)
    status = ExtractionStatus.EXTRACTED if text else ExtractionStatus.UNAVAILABLE
    return TextExtraction(text, status, None if text else "no text layer (scanned PDF?)", "application/pdf", sections)


def _docx(data: bytes) -> TextExtraction:
    import io

    import docx

    d = docx.Document(io.BytesIO(data))
    sections, heading, buf = [], "preamble", []
    for p in d.paragraphs:
        if p.style is not None and p.style.name.lower().startswith("heading"):
            if buf:
                sections.append((heading, "\n".join(buf)))
            heading, buf = p.text.strip() or heading, []
        elif p.text.strip():
            buf.append(p.text.strip())
    if buf:
        sections.append((heading, "\n".join(buf)))
    for ti, table in enumerate(d.tables, 1):
        rows = [" | ".join(c.text.strip() for c in r.cells) for r in table.rows]
        sections.append((f"table {ti}", "\n".join(rows)))
    text = "\n\n".join(t for _, t in sections)
    return TextExtraction(text, ExtractionStatus.EXTRACTED, None, MEDIA_TYPES[SourceType.WORD], sections)


def _pptx(data: bytes) -> TextExtraction:
    import io

    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    sections = []
    for i, slide in enumerate(prs.slides, 1):
        parts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
        if parts:
            sections.append((f"slide {i}", "\n".join(parts)))
    text = "\n\n".join(t for _, t in sections)
    return TextExtraction(text, ExtractionStatus.EXTRACTED, None, MEDIA_TYPES[SourceType.POWERPOINT], sections)


def _xlsx(data: bytes, filename: str | None) -> TextExtraction:
    import io

    if filename and filename.lower().endswith(".csv"):
        text = data.decode("utf-8", errors="replace")
        return TextExtraction(text, ExtractionStatus.EXTRACTED, None, "text/csv", [("csv", text)])
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sections = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            sections.append((f"sheet {ws.title}", "\n".join(rows)))
    text = "\n\n".join(t for _, t in sections)
    return TextExtraction(text, ExtractionStatus.EXTRACTED, None, MEDIA_TYPES[SourceType.SPREADSHEET], sections)


def _html(data: bytes) -> TextExtraction:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    sections, heading, buf = [], soup.title.string.strip() if soup.title and soup.title.string else "page", []
    body = soup.body or soup
    for el in body.find_all(["h1", "h2", "h3", "p", "li", "td", "pre"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if el.name in {"h1", "h2", "h3"}:
            if buf:
                sections.append((heading, "\n".join(buf)))
            heading, buf = txt, []
        else:
            buf.append(txt)
    if buf:
        sections.append((heading, "\n".join(buf)))
    text = "\n\n".join(t for _, t in sections)
    if not text:
        raw = data.decode("utf-8", errors="replace").strip()
        if raw and "<" not in raw[:200]:          # a plain-text or markdown URL, not HTML
            return TextExtraction(raw, ExtractionStatus.EXTRACTED, None, "text/plain", _paragraphs(raw))
    status = ExtractionStatus.EXTRACTED if text else ExtractionStatus.UNAVAILABLE
    return TextExtraction(text, status, None, "text/html", sections)


# ------------------------------------------------------------------ text → candidate statements


@dataclass
class CandidateStatement:
    title: str
    statement: str
    knowledge_type: KnowledgeType
    locator: str | None
    excerpt: str
    confidence: float
    tags: list[str] = field(default_factory=list)
    normalized_meaning: str = ""
    graph_group: str | None = None
    scope_hint: str | None = None   # "instance" | "domain" | "parent_domain" | "structure" | None


_EXTRACT_SYSTEM = (
    "You extract discrete, independently governable knowledge statements from enterprise documents for a "
    "knowledge governance system. Each statement must be a single fact, rule, policy, process step, "
    "definition, constraint, condition, relationship or state transition that a reviewer could approve or "
    "reject on its own. Do not summarize; do not merge distinct rules; do not invent anything not in the text. "
    "Return ONLY a JSON array."
)

_EXTRACT_PROMPT = """Document title: {title}
Section locator: {locator}

TEXT:
\"\"\"
{text}
\"\"\"

Return a JSON array of objects with keys:
  title (≤ 80 chars), statement (one sentence, self-contained, keeps numbers/thresholds verbatim),
  knowledge_type (one of: {types}),
  normalized_meaning (a canonical paraphrase: subject, predicate, value, condition — no stylistic words),
  excerpt (the verbatim span of the text the statement comes from),
  confidence (0–1 that the statement is genuinely asserted by the text),
  tags (0–5 short lowercase tags),
  graph_group (the business area it belongs to, e.g. "Refunds", "Onboarding", or null),
  scope_hint ("instance" if it names or clearly concerns one specific company/site/merchant, "domain" if it
  speaks for the whole business type, "structure" if it is universal, else null).
"""

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_MODAL = re.compile(r"\b(must|shall|should|require[sd]?|may not|cannot|is required|are required|within|before|after|"
                    r"only if|unless|at least|at most|no more than|greater than|above|below|exceed\w*|threshold|"
                    r"approv\w*|means|is defined as|refers to|consists of|transitions? to|becomes|is responsible)\b", re.I)
_NUMBER = re.compile(r"\$?\d[\d,]*(\.\d+)?%?")


class CandidateExtractor:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def extract(self, *, title: str, sections: list[tuple[str, str]], text: str) -> list[CandidateStatement]:
        if not sections and text.strip():
            sections = [("¶1", text.strip())]
        if self.provider is not None and getattr(self.provider, "name", "") != "stub":
            return self._llm(title, sections)
        if self.provider is not None:
            got = self._llm(title, sections)
            if got:
                return got
        return self._heuristic(sections)

    def _llm(self, title: str, sections: list[tuple[str, str]]) -> list[CandidateStatement]:
        out: list[CandidateStatement] = []
        types = ", ".join(t.value for t in KnowledgeType)
        for locator, text in _chunk(sections, 6000):
            items = complete_json(self.provider, _EXTRACT_PROMPT.format(title=title, locator=locator, text=text, types=types),
                                  system=_EXTRACT_SYSTEM, default=[])
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict) or not it.get("statement"):
                    continue
                try:
                    kt = KnowledgeType(it.get("knowledge_type", "fact"))
                except ValueError:
                    kt = KnowledgeType.FACT
                out.append(CandidateStatement(
                    title=str(it.get("title") or it["statement"])[:80],
                    statement=str(it["statement"]).strip(),
                    knowledge_type=kt,
                    locator=locator,
                    excerpt=str(it.get("excerpt") or it["statement"]),
                    confidence=float(it.get("confidence", 0.6) or 0.6),
                    tags=[str(t).lower() for t in (it.get("tags") or [])][:5],
                    normalized_meaning=str(it.get("normalized_meaning") or normalize(it["statement"])),
                    graph_group=it.get("graph_group") or None,
                    scope_hint=(it.get("scope_hint") or None),
                ))
        return out

    @staticmethod
    def _heuristic(sections: list[tuple[str, str]]) -> list[CandidateStatement]:
        out: list[CandidateStatement] = []
        for locator, text in sections:
            for sentence in _SENTENCE.split(" ".join(text.split())):
                s = sentence.strip()
                if len(s) < 25 or len(s) > 600:
                    continue
                if not _MODAL.search(s):
                    continue
                kt = classify_statement(s)
                conf = 0.55 + (0.15 if _NUMBER.search(s) else 0) + (0.1 if kt != KnowledgeType.FACT else 0)
                out.append(CandidateStatement(
                    title=_title_for(s), statement=s, knowledge_type=kt, locator=locator, excerpt=s,
                    confidence=round(min(conf, 0.9), 2), normalized_meaning=normalize(s), graph_group=locator if locator and not locator.startswith(("¶", "p.", "slide")) else None,
                ))
        return out


def _chunk(sections: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    out, buf, locs, size = [], [], [], 0
    for loc, text in sections:
        if size + len(text) > limit and buf:
            out.append((" / ".join(locs), "\n\n".join(buf)))
            buf, locs, size = [], [], 0
        buf.append(text)
        locs.append(loc)
        size += len(text)
    if buf:
        out.append((" / ".join(locs), "\n\n".join(buf)))
    return out


def classify_statement(s: str) -> KnowledgeType:
    low = s.lower()
    if re.search(r"\b(is defined as|means|refers to|definition)\b", low):
        return KnowledgeType.DEFINITION
    if re.search(r"\b(transitions? to|becomes|moves? to|changes? (status|state) to)\b", low):
        return KnowledgeType.STATE_TRANSITION
    if re.search(r"\b(policy|policies)\b", low):
        return KnowledgeType.POLICY
    if re.search(r"\b(step|then|after|before|first|next|finally|followed by)\b", low) and re.search(r"\b(process|procedure|workflow)\b", low):
        return KnowledgeType.PROCESS_STEP
    if re.search(r"\b(only if|unless|provided that|when|if)\b", low) and not re.search(r"\b(must|shall|required)\b", low):
        return KnowledgeType.CONDITION
    if re.search(r"\b(must not|cannot|may not|no more than|at most|maximum|limit)\b", low):
        return KnowledgeType.CONSTRAINT
    if re.search(r"\b(must|shall|required|requires|approval|threshold|within)\b", low):
        return KnowledgeType.RULE
    if re.search(r"\b(owns|belongs to|is part of|consists of|relates to|responsible for)\b", low):
        return KnowledgeType.RELATIONSHIP
    return KnowledgeType.FACT


_STOP = {"the", "a", "an", "of", "to", "and", "or", "is", "are", "be", "for", "in", "on", "at", "by", "with", "that",
         "this", "it", "its", "as", "from", "all", "any", "will", "shall", "must", "should", "required", "require",
         "requires", "than", "then", "if", "when", "which", "who", "whom", "their", "there", "has", "have", "had"}


def normalize(statement: str) -> str:
    """Canonical token form used for duplicate / conflict comparison: lowercase, no stop words, numbers
    kept, currency/percent symbols stripped, trivial plurals folded."""
    s = statement.lower()
    s = re.sub(r"[\$€£]", " ", s)
    s = re.sub(r"(\d),(\d)", r"\1\2", s)
    tokens = re.findall(r"[a-z0-9.%]+", s)
    out = []
    for t in tokens:
        t = t.strip(".")
        if not t or t in _STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return " ".join(out)


def _title_for(s: str) -> str:
    words = re.findall(r"[A-Za-z0-9$%,.]+", s)
    return " ".join(words[:8]).rstrip(",.") + ("…" if len(words) > 8 else "")


def to_json(items: list[CandidateStatement]) -> str:  # for debugging / CLI
    return json.dumps([i.__dict__ for i in items], default=str, indent=2)
