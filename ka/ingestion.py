"""knowledge-ingestion (§3.1, §4.1): Upload / Paste / Write / Link / Connect, all landing as immutable
Source + SourceVersion records. Ingestion never produces governed knowledge; it emits `source.ingested`
and hands text to extraction. Raw bytes are kept beside the JSON so the original can always be re-read.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ka.audit import Auditor
from ka.events import EventBus
from ka.extraction import TextExtraction, extract_text, source_type_for_filename
from ka.model import Scope, Source, SourceVersion
from ka.repository import Repository
from ka.security import UnsafeURL, is_safe_url, safe_fetch
from ka.vocab import AcquisitionChannel, AuthorityType, ExtractionStatus, SourceType, Visibility


@dataclass
class Ingested:
    source: Source
    version: SourceVersion
    extraction: TextExtraction
    is_new_version: bool


class IngestionService:
    def __init__(self, repo: Repository, bus: EventBus, auditor: Auditor):
        self.repo, self.bus, self.auditor = repo, bus, auditor
        self.blob_dir = repo.root / "blobs"

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
             fetch: bool = True, prefetched: bytes | None = None, timeout: float = 20.0) -> Ingested:
        st = SourceType.GITHUB if "github.com" in url else SourceType.URL
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
                           visibility=visibility, location=url)
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
                            extraction_note=extraction.note)
        if data:
            self.blob_dir.mkdir(parents=True, exist_ok=True)
            blob = self.blob_dir / f"{ver.id}{Path(filename).suffix if filename else '.bin'}"
            blob.write_bytes(data)
            ver.stored_path = str(blob)
        self.repo.source_versions.put(ver)
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
