"""knowledge-conflict (§10, §11): find existing related knowledge, then classify each pair as
DUPLICATES / SUPPORTS / EXTENDS / REFINES / CONTRADICTS / CONTEXTUALIZES / SPECIALIZES / SUPERSEDES / …

Detection is lexical and structural (token overlap, shared subject, differing values, scope relation);
an LLM, when available, is asked only to EXPLAIN a suspected conflict and suggest a resolution (§33).
The classification is stored as a KnowledgeRelationship with its explanation so a reviewer sees why.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ka import config
from ka.extraction import normalize
from ka.llm import LLMProvider, complete_json
from ka.model import KnowledgeNuggetVersion, Scope
from ka.vocab import RelationshipType, is_broader

_NUM = re.compile(r"\d+(?:\.\d+)?")
_QUALIFIER = re.compile(r"\b(international|domestic|online|in-store|retail|wholesale|weekend|weekday|premium|standard|"
                        r"enterprise|small|large|new|existing|first|repeat|card|cash|cross-border|non-eu|eu|us|uk)\b", re.I)
_NEGATION = re.compile(r"\b(not|never|no|without|prohibited|forbidden)\b", re.I)


def tokens(statement: str) -> set[str]:
    return set(normalize(statement).split())


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / (len(ta) + len(tb) - inter)


def subject_similarity(a: str, b: str) -> float:
    """Overlap once numbers are removed: 'approval above $500' vs 'approval above $1,000' share a subject."""
    ta, tb = tokens(_NUM.sub(" ", a)), tokens(_NUM.sub(" ", b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / (len(ta) + len(tb) - inter)


@dataclass
class Finding:
    existing: KnowledgeNuggetVersion
    relationship: RelationshipType
    confidence: float
    explanation: str
    both_valid: bool | None = None
    suggested_resolution: str | None = None
    llm: dict | None = None


@dataclass
class Analysis:
    findings: list[Finding] = field(default_factory=list)

    @property
    def duplicates(self) -> list[Finding]:
        return [f for f in self.findings if f.relationship == RelationshipType.DUPLICATES]

    @property
    def conflicts(self) -> list[Finding]:
        return [f for f in self.findings if f.relationship == RelationshipType.CONTRADICTS]

    @property
    def supersession_candidates(self) -> list[Finding]:
        return [f for f in self.findings if f.relationship in {RelationshipType.CONTRADICTS, RelationshipType.SUPERSEDES}]

    def has_conflict(self) -> bool:
        return bool(self.conflicts)


# [block plan-11] research-02 R3 (Q10): statements came from documents — fenced and declared untrusted
from ka.prompting import UNTRUSTED_NOTICE, fence   # noqa: E402
# [/block plan-11]

_EXPLAIN_PROMPT = """Two knowledge statements in an enterprise knowledge base appear to conflict. """ + UNTRUSTED_NOTICE + """

EXISTING (scope {es}, authority {ea}, effective {ef}):
{e}

NEW CANDIDATE (scope {cs}, authority {ca}, effective {cf}):
{c}

Return a JSON object with keys:
  why_conflict: one or two sentences on why they appear to conflict,
  both_valid: true if both could be valid in different contexts (e.g. one is a specialization), else false,
  relationship: one of CONTRADICTS, SPECIALIZES, CONTEXTUALIZES, REFINES, EXTENDS, SUPERSEDES, DUPLICATES,
  suggested_resolution: one of "Keep Existing", "Accept New", "Merge", "Both Valid — Add Context", "Change Scope", "Request More Research",
  rationale: one sentence.
You recommend only; a human governs."""


class ConflictDetector:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def related(self, candidate: KnowledgeNuggetVersion, pool: list[KnowledgeNuggetVersion]) -> list[tuple[KnowledgeNuggetVersion, float]]:
        threshold = config.get("KA_RELATED_THRESHOLD")
        out = []
        for n in pool:
            if n.canonical_id == candidate.canonical_id and n.version == candidate.version:
                continue
            s = max(similarity(candidate.statement, n.statement),
                    similarity(candidate.normalized_meaning or candidate.statement, n.normalized_meaning or n.statement))
            sub = subject_similarity(candidate.statement, n.statement)
            score = max(s, sub * 0.9)
            if score >= threshold:
                out.append((n, round(score, 3)))
        return sorted(out, key=lambda t: -t[1])

    def analyze(self, candidate: KnowledgeNuggetVersion, pool: list[KnowledgeNuggetVersion], *, explain: bool = True) -> Analysis:
        analysis = Analysis()
        for existing, score in self.related(candidate, pool):
            f = self._classify(candidate, existing, score)
            if f.relationship == RelationshipType.CONTRADICTS and explain and self.provider is not None:
                self._explain(candidate, existing, f)
            analysis.findings.append(f)
        return analysis

    # ---- classification ---------------------------------------------------------------------------

    def _classify(self, c: KnowledgeNuggetVersion, e: KnowledgeNuggetVersion, score: float) -> Finding:
        dup_t = config.get("KA_DUPLICATE_THRESHOLD")
        c_nums, e_nums = _NUM.findall(c.statement.replace(",", "")), _NUM.findall(e.statement.replace(",", ""))
        same_subject = subject_similarity(c.statement, e.statement) >= 0.5
        c_qual, e_qual = set(q.lower() for q in _QUALIFIER.findall(c.statement)), set(q.lower() for q in _QUALIFIER.findall(e.statement))
        c_neg, e_neg = bool(_NEGATION.search(c.statement)), bool(_NEGATION.search(e.statement))
        c_scope, e_scope = c.scope, e.scope
        scope_rel = _scope_relation(c_scope, e_scope)

        if score >= dup_t and c_nums == e_nums and c_neg == e_neg:
            return Finding(e, RelationshipType.DUPLICATES, score, f"token similarity {score:.2f} with identical values")

        if same_subject and (c_nums != e_nums or c_neg != e_neg):
            # Same subject, different value. Qualifiers or a narrower scope make it a specialization, not a contradiction.
            if c_qual - e_qual:
                return Finding(e, RelationshipType.SPECIALIZES, round(score, 2),
                               f"same subject, different value, but candidate carries qualifier(s) {sorted(c_qual - e_qual)} — contextual specialization",
                               both_valid=True, suggested_resolution="Both Valid — Add Context")
            if e_qual - c_qual:
                return Finding(e, RelationshipType.CONTEXTUALIZES, round(score, 2),
                               f"existing is the qualified case {sorted(e_qual - c_qual)}; candidate states the general case",
                               both_valid=True, suggested_resolution="Both Valid — Add Context")
            if scope_rel == "narrower":
                return Finding(e, RelationshipType.SPECIALIZES, round(score, 2),
                               f"candidate scope {c_scope.key()} is narrower than existing {e_scope.key()} — an override, not a contradiction",
                               both_valid=True, suggested_resolution="Accept New")
            if scope_rel == "same":
                return Finding(e, RelationshipType.CONTRADICTS, round(max(score, 0.6), 2),
                               f"same subject and scope, different value: {e_nums or ('negated' if e_neg else '')} vs {c_nums or ('negated' if c_neg else '')}",
                               both_valid=False, suggested_resolution="Accept New" if _newer(c, e) else "Keep Existing")
            if scope_rel == "broader":
                # The existing nugget is a narrower-scope override; a new general rule does not contradict it (§9).
                return Finding(e, RelationshipType.CONTEXTUALIZES, round(max(score, 0.5), 2),
                               f"existing {e_scope.key()} is a narrower override of the candidate's general rule at {c_scope.key()} — override preserved",
                               both_valid=True, suggested_resolution="Both Valid — Add Context")
            return Finding(e, RelationshipType.INDEPENDENT_OF, round(score, 2), "same subject in unrelated scopes")

        if same_subject and len(tokens(c.statement)) > len(tokens(e.statement)) + 3:
            return Finding(e, RelationshipType.EXTENDS, round(score, 2), "candidate adds detail to the same subject")
        if same_subject and score >= 0.5:
            return Finding(e, RelationshipType.SUPPORTS, round(score, 2), "same subject and consistent values")
        if same_subject:
            return Finding(e, RelationshipType.REFINES, round(score, 2), "same subject, re-worded")
        return Finding(e, RelationshipType.INDEPENDENT_OF, round(score, 2), "weakly related")

    def _explain(self, c: KnowledgeNuggetVersion, e: KnowledgeNuggetVersion, f: Finding) -> None:
        got = complete_json(self.provider, _EXPLAIN_PROMPT.format(
            es=e.scope.key(), ea=e.authority_type.value, ef=e.effective_from or "n/a", e=fence(e.statement, "existing"),
            cs=c.scope.key(), ca=c.authority_type.value, cf=c.effective_from or "n/a", c=fence(c.statement, "candidate")), default=None)
        if isinstance(got, dict):
            f.llm = got
            if isinstance(got.get("both_valid"), bool):
                f.both_valid = got["both_valid"]
            if got.get("suggested_resolution"):
                f.suggested_resolution = str(got["suggested_resolution"])
            rel = str(got.get("relationship", "")).upper()
            if rel in RelationshipType.__members__ and f.both_valid and rel != "CONTRADICTS":
                f.relationship = RelationshipType(rel)
                f.explanation += f" | LLM: {got.get('why_conflict', '')}"


def _scope_relation(c: Scope, e: Scope) -> str:
    if c.key() == e.key():
        return "same"
    if is_broader(e.scope_type, c.scope_type):
        return "narrower"
    if is_broader(c.scope_type, e.scope_type):
        return "broader"
    return "unrelated"


def _newer(c: KnowledgeNuggetVersion, e: KnowledgeNuggetVersion) -> bool:
    return (c.effective_from or c.created_at) >= (e.effective_from or e.created_at)
