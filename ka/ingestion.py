"""knowledge-ingestion (§3.1, §4.1): Upload / Paste / Write / Link / Connect, all landing as immutable
Source + SourceVersion records. Ingestion never produces governed knowledge; it emits `source.ingested`
and hands text to extraction. Raw bytes are kept beside the JSON so the original can always be re-read.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ka import config
from ka.audit import Auditor
from ka.events import EventBus
from ka.extraction import EXTRACTION_VERSION, TextExtraction, extract_text, source_type_for_filename
from ka.model import PhysicalBinding, Scope, Source, SourceVersion
from ka.physical import LocalPhysicalStore, PhysicalRef, PhysicalStore, binding_key
from ka.repository import Repository
from ka.security import UnsafeURL, is_safe_url, safe_fetch
from ka.timeutil import now_iso as _now_iso
from ka.vocab import AcquisitionChannel, AuthorityType, ExtractionStatus, SourceType, Visibility


@dataclass
class Ingested:
    source: Source
    version: SourceVersion
    extraction: TextExtraction
    is_new_version: bool


class IngestionService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor, physical: PhysicalStore | None = None):
        self.repo, self.bus, self.auditor = repo, bus, auditor
        self.blob_dir = repo.root / "blobs"
        self.physical: PhysicalStore = physical or LocalPhysicalStore(repo.root)      # plan-18: the port beneath the funnel

    # ---- public entry points: Upload / Paste / Write / Link / Connect ----------------------------

    def upload(self, *, filename: str, data: bytes, owner: str, scope: Scope | None = None, title: str | None = None,
               authority: AuthorityType = AuthorityType.PROJECT_DOCUMENTATION, visibility: Visibility = Visibility.ENTERPRISE,
               source_type: SourceType | None = None, effective_date: str | None = None, author: str | None = None) -> Ingested:
        st = source_type or source_type_for_filename(filename)
        return self._ingest(title=title or filename, data=data, source_type=st, owner=owner, scope=scope, authority=authority,
                            visibility=visibility, filename=filename, location=filename, effective_date=effective_date, author=author)

    def paste(self, *, text: str, owner: str, scope: Scope | None = None, title: str = "Pasted text",
              authority: AuthorityType = AuthorityType.USER_KNOWLEDGE, visibility: Visibility = Visibility.ENTERPRISE,
              markdown: bool = False) -> Ingested:
        st = SourceType.MARKDOWN if markdown else SourceType.TEXT
        return self._ingest(title=title, data=text.encode("utf-8"), source_type=st, owner=owner, scope=scope,
                            authority=authority, visibility=visibility)

    def write_note(self, *, text: str, owner: str, scope: Scope | None = None, title: str = "Note",
                   authority: AuthorityType = AuthorityType.USER_KNOWLEDGE, visibility: Visibility = Visibility.PERSONAL) -> Ingested:
        return self._ingest(title=title, data=text.encode("utf-8"), source_type=SourceType.NOTE, owner=owner, scope=scope,
                            authority=authority, visibility=visibility, author=owner)

    def link(self, *, url: str, owner: str, scope: Scope | None = None, title: str | None = None,
             authority: AuthorityType = AuthorityType.EXTERNAL_REFERENCE, visibility: Visibility = Visibility.ENTERPRISE,
             fetch: bool = True, prefetched: bytes | None = None, timeout: float = 20.0, metadata: dict | None = None) -> Ingested:
        st = SourceType.GITHUB if "github.com" in url else SourceType.URL
        # [block plan-07] provenance from discovery (canonical_url, publisher, published_at, query, discovered_rank) + retrieved_at
        from ka.timeutil import now_iso as _now
        metadata = {**(metadata or {}), "retrieved_at": _now()}
        # [/block plan-07]
        data = prefetched
        note = None
        # [block plan-02]
        if data is None and fetch:
            ok, why = is_safe_url(url)
            if not ok:
                note = f"blocked: {why}"
                data = b""
                self.auditor.record(who=owner, what="source.blocked", why=why, scope=scope, affected=[url])
            else:
                try:
                    fetched = safe_fetch(url, timeout=timeout)
                    data = fetched.content
                    if "text/plain" in fetched.content_type or "markdown" in fetched.content_type:
                        st = SourceType.MARKDOWN if url.endswith(".md") else SourceType.TEXT
                except UnsafeURL as e:
                    note = f"blocked: {e}"
                    data = b""
                    self.auditor.record(who=owner, what="source.blocked", why=str(e), scope=scope, affected=[url])
                except Exception as e:  # noqa: BLE001
                    note = f"fetch failed: {type(e).__name__}: {e}"
                    data = b""
        # [/block plan-02]
        elif data is None:
            data = b""
            note = "not fetched"
        got = self._ingest(title=title or url, data=data, source_type=st, owner=owner, scope=scope, authority=authority,
                           visibility=visibility, location=url, metadata=metadata)
        if note:
            got.version.extraction_status = ExtractionStatus.FAILED if ("failed" in note or "blocked" in note) else ExtractionStatus.PENDING
            got.version.extraction_note = note
            got.extraction.status, got.extraction.note = got.version.extraction_status, note   # the API reports the extraction object
            self.repo.source_versions.put(got.version)
            got.source.extraction_status = got.version.extraction_status
            self.repo.sources.put(got.source)
        return got

    def connect(self, *, connector: str, locator: str, payload: bytes, owner: str, scope: Scope | None = None,
                title: str | None = None, authority: AuthorityType = AuthorityType.PROJECT_DOCUMENTATION,
                visibility: Visibility = Visibility.ENTERPRISE, media_type: str = "text/plain") -> Ingested:
        """Connector-based sources: the connector has already fetched `payload`; KA records provenance."""
        return self._ingest(title=title or f"{connector}:{locator}", data=payload, source_type=SourceType.CONNECTOR, owner=owner,
                            scope=scope, authority=authority, visibility=visibility, location=f"{connector}://{locator}",
                            metadata={"connector": connector, "media_type": media_type})

    def record_derived(self, *, title: str, text: str, owner: str, scope: Scope | None, channel: AcquisitionChannel,
                       source_type: SourceType, authority: AuthorityType, visibility: Visibility, location: str | None = None,
                       metadata: dict | None = None) -> Ingested:
        """Research and correction channels record what they produced as a Source too (§16, §23), so every
        nugget has a source_ref whatever its channel."""
        return self._ingest(title=title, data=text.encode("utf-8"), source_type=source_type, owner=owner, scope=scope,
                            authority=authority, visibility=visibility, location=location, channel=channel, metadata=metadata or {})

    # [block plan-04]
    def reextract(self, source_id: str, *, owner: str) -> Ingested:
        """research-01 R16: run the current extractor over the stored bytes as a NEW SourceVersion (same checksum,
        new extraction_version). The only path that bypasses same-bytes dedupe, deliberately."""
        src = self.repo.sources.require(source_id)
        cur = self.repo.source_versions.get(src.current_version_id or "")
        if cur is None:
            raise ValueError(f"source {source_id} has no stored bytes to re-extract (blocked or not fetched)")
        # plan-18: read through the physical store via the binding; legacy versions fall back to stored_path
        b = self.repo.binding_for_version(cur.id)
        if b is not None and b.status != "available":
            raise ValueError(f"source {source_id} has no stored bytes to re-extract — version {cur.version} is not available ({b.status}: {b.reason or 'no reason recorded'})")
        if b is not None and b.backend == self.physical.name:
            data = self.physical.get(PhysicalRef(backend=b.backend, asset_id=b.dp_asset_id or "", asset_version_id=b.dp_asset_version_id or "1",
                                                 sha256=b.sha256, locator=b.locator))
        elif cur.stored_path and Path(cur.stored_path).exists():
            data = Path(cur.stored_path).read_bytes()
        else:
            raise ValueError(f"source {source_id} has no stored bytes to re-extract (blocked or not fetched)")
        extraction = extract_text(data, src.source_type, src.original_filename)
        src.content_version += 1
        ver = SourceVersion(source_id=src.id, version=src.content_version, checksum=cur.checksum, media_type=extraction.media_type,
                            text=extraction.text, byte_size=len(data), stored_path=cur.stored_path, extraction_status=extraction.status,
                            extraction_note=extraction.note, extraction_version=EXTRACTION_VERSION)
        self.repo.source_versions.put(ver)
        src.current_version_id, src.extraction_status = ver.id, extraction.status
        self.repo.sources.put(src)
        self.bus.emit("source.updated", source_id=src.id, source_version_id=ver.id)
        self.auditor.record(who=owner, what="source.reextracted", why=f"extractor {EXTRACTION_VERSION}", source=src.id, scope=src.scope,
                            before={"version": cur.version, "extraction_version": cur.extraction_version},
                            after={"version": ver.version, "extraction_version": ver.extraction_version}, affected=[src.id, ver.id])
        return Ingested(src, ver, extraction, is_new_version=True)
    # [/block plan-04]

    # ---- core ---------------------------------------------------------------------------------

    def _ingest(self, *, title, data, source_type, owner, scope, authority, visibility, filename=None, location=None,
                effective_date=None, author=None, channel=AcquisitionChannel.CONTENT, metadata=None) -> Ingested:
        checksum = hashlib.sha256(data).hexdigest()
        existing = self._find_existing(location, title, owner)
        extraction = extract_text(data, source_type, filename)

        if existing and existing.current_version_id:
            cur = self.repo.source_versions.get(existing.current_version_id)
            if cur and cur.checksum == checksum:
                return Ingested(existing, cur, extraction, is_new_version=False)

        if existing:
            src = existing
            src.content_version += 1
            is_new = True
        else:
            src = Source(source_type=source_type, channel=channel, title=title, original_location=location, original_filename=filename,
                         owner=owner, author=author, checksum=checksum, visibility=visibility, permissions=[owner],
                         scope=scope, domain_id=scope.scope_id if scope and scope.scope_type.value == "DOMAIN" else None,
                         instance_id=scope.scope_id if scope and scope.scope_type.value == "INSTANCE" else None,
                         effective_date=effective_date, authority_type=authority, metadata=metadata or {})
            is_new = False

        ver = SourceVersion(source_id=src.id, version=src.content_version, checksum=checksum, media_type=extraction.media_type,
                            text=extraction.text, byte_size=len(data), extraction_status=extraction.status,
                            extraction_note=extraction.note, extraction_version=EXTRACTION_VERSION)
        # [block plan-18] research-03 R2/R3: bytes go through the physical store; the binding says where they are and whether the
        # version is available. The local store writes the same blob path as before, so `stored_path` keeps working.
        tenant = config.get("KA_TENANT_ID") or "default"
        key = binding_key(tenant, src.id, src.content_version)
        binding = PhysicalBinding(tenant_id=tenant, ka_source_id=src.id, ka_source_version=src.content_version, source_version_id=ver.id,
                                  backend=self.physical.name, sha256=checksum, owner=owner, visibility=visibility)
        if data:
            try:
                ref = self.physical.put(data, content_type=extraction.media_type, sha256=checksum, idempotency_key=f"{key}:{ver.id}",
                                        owner=owner, visibility=visibility.value, tenant_id=tenant, filename_hint=filename)
                if ref.sha256 != checksum:
                    raise ValueError(f"physical store returned sha {ref.sha256[:12]}… for bytes with sha {checksum[:12]}…")
                binding.status, binding.locator = ref.state, ref.locator
                binding.dp_asset_id, binding.dp_asset_version_id = ref.asset_id, ref.asset_version_id
                if ref.backend == "local":
                    ver.stored_path = ref.locator
            except Exception as e:  # noqa: BLE001 — a failed physical write never yields an available version
                binding.status, binding.reason = "failed", f"{type(e).__name__}: {e}"
        else:
            binding.status, binding.reason = "failed", extraction.note or "no bytes (blocked or empty)"
        binding.last_synced_at = _now_iso()
        self.repo.source_versions.put(ver)
        self.repo.put_binding(binding)
        # [/block plan-18]
        src.checksum = checksum
        src.current_version_id = ver.id
        src.extraction_status = extraction.status
        self.repo.sources.put(src)

        self.bus.emit("source.updated" if is_new else "source.ingested", source_id=src.id, source_version_id=ver.id)
        self.auditor.record(who=owner, what="source.updated" if is_new else "source.ingested",
                            why=f"{source_type.value} via {channel.value}", source=src.id, scope=scope,
                            after={"checksum": checksum, "extraction_status": extraction.status.value},
                            affected=[src.id, ver.id])
        return Ingested(src, ver, extraction, is_new_version=is_new)

    def _find_existing(self, location: str | None, title: str, owner: str) -> Source | None:
        if location:
            hits = self.repo.sources.where(lambda s: s.original_location == location and s.owner == owner)
            if hits:
                return hits[0]
        return None
