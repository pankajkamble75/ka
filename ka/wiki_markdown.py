# [block plan-26]
"""The wiki's editing syntax (research-04 R5; §8a "No HTML"): a Markdown SUBSET parsed server-side into the plan-25 block shape, a
serializer that round-trips it, and a block diff by stable id. Anything outside the grammar — any `<…>` tag, a non-http(s) link, a
`javascript:`/`data:` URL, a comment other than the block-id form — is refused with the offending line; nothing is ever stored as HTML
and the console renders block text only through its escaping helper."""
from __future__ import annotations

import re
from typing import Any

MAX_LINE = 4000
ID_COMMENT = re.compile(r"^<!--\s*([A-Za-z]\w{0,31})\s*-->$")
HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
ULIST = re.compile(r"^[-*]\s+(.*)$")
OLIST = re.compile(r"^\d+[.)]\s+(.*)$")
QUOTE = re.compile(r"^>\s?(.*)$")
TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
TAG = re.compile(r"<\s*/?\s*[A-Za-z!?]")
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
REF = re.compile(r"\[\[([A-Z]+-[0-9A-Za-z]+:v\d+)\]\]")
SAFE_URL = re.compile(r"^https?://[^\s<>\"']+$", re.I)
IMAGE_URL = re.compile(r"^image:(\d{1,6})$")


class MarkdownRefused(ValueError):
    def __init__(self, line_no: int, line: str, why: str):
        super().__init__(f"line {line_no}: {why} — {line.strip()[:80]!r}")
        self.line_no, self.line, self.why = line_no, line, why


def _check_inline(line_no: int, line: str) -> None:
    if len(line) > MAX_LINE:
        raise MarkdownRefused(line_no, line, f"line longer than {MAX_LINE} characters")
    if TAG.search(line) and not ID_COMMENT.match(line.strip()):
        raise MarkdownRefused(line_no, line, "HTML is not allowed; use the Markdown subset")
    for m in IMAGE.finditer(line):
        if not IMAGE_URL.match(m.group(2)):
            raise MarkdownRefused(line_no, line, "images must reference the image store as image:<number>")
    for m in LINK.finditer(IMAGE.sub("", line)):
        if not SAFE_URL.match(m.group(2)):
            raise MarkdownRefused(line_no, line, "links must be http(s) URLs")
    low = line.lower()
    if "javascript:" in low or "data:" in low and "](data:" in low:
        raise MarkdownRefused(line_no, line, "javascript: and data: URLs are not allowed")


def parse(text: str) -> list[dict[str, Any]]:
    """Markdown subset → blocks `{id, kind, text, level, items?, rows?}`; `refs` are the citations each block names."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    pending_id: str | None = None
    para: list[str] = []
    list_items: list[str] = []
    list_ordered = False
    quote: list[str] = []
    table: list[str] = []
    n = 0

    def new_block(kind: str, txt: str, **extra) -> None:
        nonlocal pending_id, n
        n += 1
        b = {"id": pending_id or f"n{n}", "kind": kind, "text": txt, "level": extra.pop("level", 2), "refs": sorted(set(REF.findall(txt + " " + " ".join(extra.get("items", [])) + " " + " ".join(" ".join(r) for r in extra.get("rows", [])))))}
        b.update(extra)
        blocks.append(b)
        pending_id = None

    def flush() -> None:
        nonlocal para, list_items, quote, table
        if para:
            new_block("paragraph", " ".join(s.strip() for s in para)); para = []
        if list_items:
            new_block("list", "", items=list_items, ordered=list_ordered); list_items = []
        if quote:
            new_block("quote", " ".join(quote)); quote = []
        if table:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table if not TABLE_SEP.match(r)]
            new_block("table", "", rows=rows); table = []

    for i, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if not line.strip():
            flush(); continue
        m = ID_COMMENT.match(line.strip())
        if m:
            flush(); pending_id = m.group(1); continue
        _check_inline(i, line)
        if (m := HEADING.match(line)):
            flush(); new_block("heading", m.group(2), level=len(m.group(1))); continue
        if (m := ULIST.match(line)) or (m := OLIST.match(line)):
            if para or quote or table:
                flush()
            ordered = bool(OLIST.match(line))
            if list_items and ordered != list_ordered:
                flush()
            list_ordered = ordered; list_items.append(m.group(1).strip()); continue
        if (m := QUOTE.match(line)):
            if para or list_items or table:
                flush()
            quote.append(m.group(1).strip()); continue
        if line.strip().startswith("|"):
            if para or list_items or quote:
                flush()
            table.append(line); continue
        if list_items or quote or table:
            flush()
        para.append(line)
    flush()
    return blocks


def to_markdown(blocks: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for b in blocks:
        out.append(f"<!-- {b['id']} -->")
        kind = b.get("kind", "paragraph")
        if kind == "heading":
            out.append("#" * max(1, min(int(b.get("level", 2)), 3)) + " " + b.get("text", ""))
        elif kind == "list":
            items = b.get("items", [])
            for k, it in enumerate(items, 1):
                txt = it["text"] + (f" [[{it['ref']}]]" if it.get("ref") else "") if isinstance(it, dict) else str(it)
                out.append(f"{k}. {txt}" if b.get("ordered") else f"- {txt}")
        elif kind == "quote":
            out.append("> " + b.get("text", ""))
        elif kind == "table":
            rows = b.get("rows", [])
            if rows:
                out.append("| " + " | ".join(rows[0]) + " |")
                out.append("|" + "---|" * len(rows[0]))
                for r in rows[1:]:
                    out.append("| " + " | ".join(r) + " |")
        else:
            out.append(b.get("text", ""))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _content(b: dict[str, Any]) -> tuple:
    kind = b.get("kind", "paragraph")
    if kind == "list":
        return (kind, bool(b.get("ordered")), tuple((it["text"] + (f" [[{it['ref']}]]" if it.get("ref") else "")) if isinstance(it, dict) else str(it) for it in b.get("items", [])))
    if kind == "table":
        return (kind, tuple(tuple(r) for r in b.get("rows", [])))
    return (kind, int(b.get("level", 2)) if kind == "heading" else 0, (b.get("text") or "").strip())


def block_diff(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """insert / update / delete / move by stable id; unaffected blocks are absent."""
    old_by = {b["id"]: b for b in old}
    new_by = {b["id"]: b for b in new}
    old_ids = [b["id"] for b in old]
    new_ids = [b["id"] for b in new]
    diff: list[dict[str, Any]] = []
    for b in old:
        if b["id"] not in new_by:
            diff.append({"block_id": b["id"], "op": "delete", "before": b, "after": None})
    for b in new:
        if b["id"] not in old_by:
            diff.append({"block_id": b["id"], "op": "insert", "before": None, "after": b})
        elif _content(old_by[b["id"]]) != _content(b):
            diff.append({"block_id": b["id"], "op": "update", "before": old_by[b["id"]], "after": b})
    common_old = [i for i in old_ids if i in new_by]
    common_new = [i for i in new_ids if i in old_by]
    if common_old != common_new:
        moved = {i for i, j in zip(common_old, common_new) if i != j}
        for i in moved:
            if not any(d["block_id"] == i for d in diff):
                diff.append({"block_id": i, "op": "move", "before": old_by[i], "after": new_by[i]})
    return diff
# [/block plan-26]
