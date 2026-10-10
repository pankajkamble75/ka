"""Declared settings, in the style of enterprise-os's config registry: every key is declared with a type,
a default and an owner; `get()` refuses undeclared names so a typo cannot silently fall back to a default.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from dotenv import load_dotenv

from ka.vocab import DEFAULT_AUTHORITY_RANK, AuthorityType, ScopeType

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


class UnknownSetting(KeyError):
    pass


@dataclass(frozen=True)
class Setting:
    name: str
    type: Callable[[str], Any]
    default: Any
    owner: str
    doc: str

    def parse(self, raw: str | None) -> Any:
        if raw is None or raw == "":
            return self.default
        if self.type is bool:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return self.type(raw)


SETTINGS: dict[str, Setting] = {}


def declare(name: str, type_: Callable[[str], Any], default: Any, owner: str, doc: str) -> None:
    SETTINGS[name] = Setting(name, type_, default, owner, doc)


declare("KA_STORAGE_ROOT", str, "", "ka.repository", "Directory for the JSON object store. Default: <repo>/ka_storage.")
declare("KA_BACKEND_PORT", int, 8011, "ka.api", "Port the Knowledge Console backend listens on.")
declare("KA_LLM_PROVIDER", str, "", "ka.llm", "anthropic | stub. Empty: anthropic when ANTHROPIC_API_KEY is set, else stub.")
declare("ANTHROPIC_API_KEY", str, "", "ka.llm", "Anthropic API key (secret).")
declare("KA_LLM_MODEL", str, "claude-sonnet-4-6", "ka.llm", "Default model for extraction, synthesis and conflict explanation.")
declare("KA_LLM_MAX_TOKENS", int, 4000, "ka.llm", "Max output tokens per call.")
declare("KA_LLM_TIMEOUT", float, 120.0, "ka.llm", "Per-call timeout in seconds.")
declare("KA_RESEARCH_INTERNET", bool, False, "ka.research", "Allow the Internet Research Agent to fetch URLs.")
declare("KA_AUTO_RESOLVE_AUTHORITY_GAP", int, 40, "ka.governance",
        "§13: a candidate whose authority rank is at least this far below a contradicting ACTIVE nugget is auto-resolved "
        "(kept as a CONFLICT record with explanation). 0 disables.")
declare("KA_DUPLICATE_THRESHOLD", float, 0.82, "ka.conflict", "Token-similarity at or above which two statements are DUPLICATES.")
declare("KA_RELATED_THRESHOLD", float, 0.35, "ka.conflict", "Token-similarity at or above which two statements are compared at all.")
declare("KA_PROMOTION_MIN_INSTANCES", int, 3, "ka.promotion", "§25: instances that must share a statement before promotion is proposed.")
declare("KA_HIGH_IMPACT_INSTANCES", int, 5, "ka.graph_change", "A proposal touching at least this many instances requires explicit approval.")
declare("KA_ENTERPRISE_OS_ROOT", str, "", "ka.graph_adapter", "Path to an enterprise-os checkout; enables the live GraphStore adapter.")
declare("KW_STORAGE_ROOT", str, "", "ka.graph_adapter", "Enterprise OS storage root (its graph_v2 lives under it).")
# [block plan-02]
declare("KA_ACCESS_POLICY", str, "token", "ka.security", "loopback | token | open. token: loopback peers pass, others need the bearer token.")
declare("KA_ACCESS_TOKEN", str, "", "ka.security", "Bearer token non-loopback peers must present (secret). Empty = non-loopback refused.")
declare("KA_MAX_UPLOAD_MB", int, 25, "ka.api", "Largest upload body accepted by /sources/upload and /corrections/upload.")
declare("KA_URL_ALLOWLIST", str, "", "ka.security", "Comma-separated intranet hostnames link()/research may fetch even if private.")
# [/block plan-02]
# [block plan-03]
declare("KA_GRAMMAR_DIR", str, "", "ka.grammar", "Directory holding EOS grammar.json and process_types.json. Default: <KA_ENTERPRISE_OS_ROOT>/knowledge_worker/graph_model.")
# [/block plan-03]
# [block plan-04]
declare("KA_OCR", bool, False, "ka.extraction", "OCR text-less PDFs and images (needs the 'ocr' extra: pdf2image, pytesseract).")
# [/block plan-04]
# [block plan-05]
declare("KA_EOS_AUTO_ACTOR", str, "", "ka.graph_change",
        "A person's name under which KA's auto-approved low-impact proposals are published to EOS. Empty: they wait for a person.")
# [/block plan-05]
# [block plan-07]
declare("KA_SEARCH_PROVIDER", str, "none", "ka.discovery", "none | fixture. The real provider is Q5; unknown values fail closed to none.")
declare("KA_SEARCH_FIXTURE", str, "", "ka.discovery", "Path to a JSON file {query: [results]} for the fixture provider.")
declare("KA_ALLOWED_DOMAINS", str, "", "ka.discovery", "Comma-separated hosts discovery may select (suffix match). Empty: any public host.")
declare("KA_DISCOVERY_BUDGET", int, 5, "ka.discovery", "Fetches per mission from discovered results.")
declare("KA_DISCOVERY_RESULTS", int, 10, "ka.discovery", "Results asked per query.")
declare("KA_RESPECT_ROBOTS", bool, True, "ka.discovery", "Honour robots.txt for user-agent enterprise-os-ka.")
# [/block plan-07]
# [block plan-08]
declare("KA_CONNECTOR_ROOTS", str, "", "ka.connectors", "Comma-separated folders a local_folder connection may point into. Default: <storage>/inbox.")
# [/block plan-08]
# [block plan-13]
declare("KA_SEARCH_API_KEY", str, "", "ka.discovery", "Brave Search API key, read at call time; never stored or logged. Q12.")
declare("KA_SEARCH_MONTHLY_CAP", int, 1000, "ka.discovery", "Search queries allowed per calendar month across all missions.")
# [/block plan-13]
# [block plan-14]
declare("KA_M365_PERMISSION_SWEEP_EVERY", int, 10, "ka.connectors.m365", "Re-read permissions of every known item every N syncs (a permission change does not bump the Graph delta).")
# [/block plan-14]
# [block plan-16]
declare("KA_RESEARCH_MAX_SOURCES", int, 3, "ka.research", "Never-extracted sources the Enterprise Content agent re-extracts with the model per mission (most relevant first).")
# [/block plan-16]
# [block plan-18]
declare("KA_STORAGE_BACKEND", str, "local", "ka.physical", "local | data_platform. Where source bytes and derived artefacts live; data_platform needs plan-19's HTTP store.")
declare("KA_TENANT_ID", str, "default", "ka.physical", "Tenant recorded on every physical binding (research-03 R10 interim until Q4/Q16).")
# [/block plan-18]
# [block plan-19]
declare("KA_DP_BASE_URL", str, "", "ka.data_platform", "Data Platform v1 base URL (e.g. https://dp.example/). Empty: the data_platform backend fails closed to local.")
declare("KA_DP_SERVICE_TOKEN", str, "", "ka.data_platform", "Service token KA presents to the Data Platform; read at call time, never stored or logged.")
declare("KA_DP_TIMEOUT", float, 20.0, "ka.data_platform", "Per-call timeout in seconds for Data Platform requests.")
declare("KA_DP_RETRIES", int, 3, "ka.data_platform", "Attempts the plan-20 outbox makes before dead-lettering a Data Platform operation.")
# [/block plan-19]
# [block plan-20]
declare("KA_DP_OUTBOX_INTERVAL", float, 15.0, "ka.outbox", "Seconds between outbox worker runs when the backend is data_platform.")
declare("KA_DP_BACKOFF_BASE", float, 5.0, "ka.outbox", "First retry delay in seconds; doubles per attempt.")
# [/block plan-20]
# [block plan-21]
declare("KA_DP_INBOUND_INTERVAL", float, 15.0, "ka.data_platform.inbound", "Seconds between inbound Data Platform event polls (runs on the outbox worker's tick).")
# [/block plan-21]

_overrides: dict[str, Any] = {}


def get(name: str) -> Any:
    if name not in SETTINGS:
        raise UnknownSetting(name)
    if name in _overrides:
        return _overrides[name]
    return SETTINGS[name].parse(os.environ.get(name))


@contextmanager
def scoped(**values: Any) -> Iterator[None]:
    """Temporary overrides, mostly for tests."""
    for k in values:
        if k not in SETTINGS:
            raise UnknownSetting(k)
    saved = dict(_overrides)
    _overrides.update(values)
    try:
        yield
    finally:
        _overrides.clear()
        _overrides.update(saved)


def storage_root() -> Path:
    raw = get("KA_STORAGE_ROOT")
    return Path(raw) if raw else Path(__file__).resolve().parent.parent / "ka_storage"


class AuthorityPolicy:
    """§13 — authority_rank is configurable by organization/domain. Ranks are looked up per scope with
    fallback to the default table."""

    def __init__(self, overrides: dict[str, dict[AuthorityType, int]] | None = None):
        self._overrides = overrides or {}

    def rank(self, authority: AuthorityType, scope_type: ScopeType | None = None, scope_id: str | None = None) -> int:
        if scope_type and scope_id:
            table = self._overrides.get(f"{scope_type.value}:{scope_id}")
            if table and authority in table:
                return table[authority]
        return DEFAULT_AUTHORITY_RANK[authority]

    def set_rank(self, scope_type: ScopeType, scope_id: str, authority: AuthorityType, rank: int) -> None:
        self._overrides.setdefault(f"{scope_type.value}:{scope_id}", {})[authority] = rank

# [block plan-29] research-05 R2, R10: the AgentX services contract (PROPOSED v1)
declare("KA_SERVICE_ID", str, "knowledge-acquisition", "ka.agentx", "The service id KA reports to AgentX (healthz, capabilities).")
declare("KA_AGENTX_TOKEN", str, "", "ka.agentx", "Bearer token AgentX presents on /v1 (AgentX keeps it as AGENTX_KNOWLEDGE_ACQUISITION_TOKEN). "
        "Set → required on every /v1 call, also from loopback; unset → the console's access policy applies to /v1.")
# [/block plan-29]

# [block plan-30] research-05 R4: optional push registration and operation callbacks to AgentX
declare("KA_AGENTX_URL", str, "", "ka.agentx", "AgentX base URL (e.g. http://127.0.0.1:8765). Set → KA pushes its capability list to "
        "{KA_AGENTX_URL}/api/v1/services/{KA_SERVICE_ID}/capabilities on start and on demand. Unset → AgentX pulls GET /v1/capabilities.")
# [/block plan-30]

# [block plan-31] research-05 R7, R8: Knowledge Worker over HTTP; the grammar over HTTP
declare("KA_GRAPH_MODE", str, "auto", "ka.service", "Where governed graph changes go: memory | kw | eos-local | auto. auto = kw when KA_KW_URL is "
        "set, else eos-local (legacy, deprecated: imports Enterprise OS) when KA_ENTERPRISE_OS_ROOT is set, else memory.")
declare("KA_KW_URL", str, "", "ka.knowledge_worker", "Knowledge Worker base URL (e.g. http://127.0.0.1:8101); its /v1 intake receives KA's graph changes.")
declare("KA_KW_TOKEN", str, "", "ka.knowledge_worker", "KA's bearer token for Knowledge Worker (scopes graph-changes:propose, graphs:read).")
declare("KA_KW_PUBLISH_WAIT_S", float, 30.0, "ka.knowledge_worker", "How long a console apply waits for Knowledge Worker to apply a change.")
declare("KA_GRAMMAR_URL", str, "", "ka.grammar", "Knowledge Worker's GET /v1/graph-model URL. Set → the grammar is fetched over HTTP "
        "(bearer KA_KW_TOKEN) instead of read from KA_GRAMMAR_DIR / KA_ENTERPRISE_OS_ROOT.")
# [/block plan-31]
