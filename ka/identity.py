# [block plan-03]
"""Canonical subject identity (research-01 R2): "Merchant Underwriting", "Underwrite merchant applications" and
"merchant_underwriting" are one subject. Identity is (kind, canonical_key); scope is not part of it.

Resolution order: exact key → alias → normalized-name similarity within the same kind (≥ KA_DUPLICATE_THRESHOLD) → new.
"""
from __future__ import annotations

import re

from ka import config
from ka.conflict import similarity
from ka.extraction import normalize
from ka.model import SubjectRecord
from ka.repository import Repository


def canonical_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", normalize(name).replace(" ", "_") if normalize(name) else name.lower()).strip("_")
    return key[:64] or "unnamed"


class SubjectRegistry:
    def __init__(self, repo: Repository):
        self.repo = repo

    def resolve(self, kind: str, name: str, aliases: tuple[str, ...] | list[str] = (), *, first_ref: str | None = None) -> tuple[SubjectRecord, bool]:
        key = canonical_key(name)
        candidates = [canonical_key(a) for a in aliases] + [key]
        names = [name] + list(aliases)
        for rec in self.repo.subjects.where(lambda r: r.kind == kind):
            if rec.canonical_key in candidates or any(canonical_key(a) in candidates for a in rec.aliases):
                self._learn(rec, names)
                return rec, False
        threshold = config.get("KA_DUPLICATE_THRESHOLD")
        best, best_score = None, 0.0
        for rec in self.repo.subjects.where(lambda r: r.kind == kind):
            for n in names:
                for known in [rec.name] + rec.aliases:
                    s = similarity(n, known)
                    # "merchant underwriting process" names the subject "merchant underwriting": one name's tokens
                    # containing the other's (≥ 2 tokens) is a match even below the token-similarity threshold.
                    a, b = set(normalize(n).split()), set(normalize(known).split())
                    if a and b and len(a & b) >= 2 and (a <= b or b <= a):
                        s = max(s, threshold)
                    if s > best_score:
                        best, best_score = rec, s
        if best is not None and best_score >= threshold:
            self._learn(best, names)
            return best, False
        rec = SubjectRecord(canonical_key=key, kind=kind, name=name, aliases=[a for a in aliases if a != name], first_ref=first_ref)
        self.repo.subjects.put(rec)
        return rec, True

    def _learn(self, rec: SubjectRecord, names: list[str]) -> None:
        changed = False
        for n in names:
            if n != rec.name and n not in rec.aliases:
                rec.aliases.append(n)
                changed = True
        if changed:
            self.repo.subjects.put(rec)

    def add_alias(self, key: str, alias: str) -> SubjectRecord:
        rec = self.repo.subjects.require(key)
        self._learn(rec, [alias])
        return rec
# [/block plan-03]
