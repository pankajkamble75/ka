# [block plan-23]
"""Backfill rehearsal (research-03 R14): bind every legacy `SourceVersion` to the configured physical backend with SHA-256 verification.

    KA_STORAGE_BACKEND=data_platform KA_DP_BASE_URL=... KA_DP_SERVICE_TOKEN=... \\
        python tools/backfill_physical.py --storage <root> [--apply] [--publish-active]

Dry-run by default: prints what WOULD happen and writes nothing. With --apply: bytes present → upload under the ingestion key shape →
the returned sha must equal the version's checksum (else the binding is `failed: sha mismatch`, never available) → binding `available`;
no bytes → binding `failed` with the version's note. --publish-active publishes every ACTIVE nugget version as a derived artefact and
drains the outbox. Idempotent: versions with an available binding for this backend are skipped. `KA_STORAGE_BACKEND=local` is the
rollback and is never removed from the code — on the local backend --apply is refused (exit 2): there is nothing to migrate to.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ka import config  # noqa: E402
from ka.llm import StubLLMProvider  # noqa: E402
from ka.model import PhysicalBinding  # noqa: E402
from ka.physical import binding_key  # noqa: E402
from ka.service import KnowledgeAcquisition  # noqa: E402
from ka.timeutil import now_iso  # noqa: E402
from ka.vocab import NuggetStatus  # noqa: E402


def backfill(ka: KnowledgeAcquisition, *, apply: bool, publish_active: bool = False) -> dict:
    tenant = config.get("KA_TENANT_ID")
    backend = ka.physical.name
    rep = {"backend": backend, "apply": apply, "versions": 0, "skipped": 0, "would_bind": 0, "available": 0, "failed": 0, "sha_mismatch": 0,
           "conflicts": 0, "published": 0, "failures": [], "conflict_versions": []}
    for ver in sorted(ka.repo.source_versions.all(), key=lambda v: v.created_at):
        rep["versions"] += 1
        src = ka.repo.sources.get(ver.source_id)
        if src is None:
            rep["skipped"] += 1
            continue
        existing = ka.repo.binding_for_version(ver.id)
        if existing is not None and existing.backend == backend and existing.status == "available":
            rep["skipped"] += 1
            continue
        rep["would_bind"] += 1
        if not apply:
            continue
        key = binding_key(tenant, src.id, ver.version)
        data = Path(ver.stored_path).read_bytes() if ver.stored_path and Path(ver.stored_path).exists() else None
        b = existing or PhysicalBinding(tenant_id=tenant, ka_source_id=src.id, ka_source_version=ver.version, source_version_id=ver.id, backend=backend,
                                        sha256=ver.checksum, owner=src.owner, visibility=src.visibility)
        b.backend = backend
        if data is None:
            b.status, b.reason = "failed", ver.extraction_note or "no bytes (blocked or empty)"
            rep["failed"] += 1
            rep["failures"].append({"source": src.id, "version": ver.version, "reason": b.reason})
        else:
            try:
                ref = ka.physical.put(data, content_type=ver.media_type, sha256=ver.checksum, idempotency_key=f"{key}:{ver.id}", owner=src.owner,
                                      visibility=src.visibility.value, tenant_id=tenant, filename_hint=src.original_filename)
                if ref.sha256 != ver.checksum:
                    b.status, b.reason, rep["sha_mismatch"] = "failed", f"sha mismatch: store returned {ref.sha256[:12]}…, version has {ver.checksum[:12]}…", rep["sha_mismatch"] + 1
                    rep["failed"] += 1
                    rep["failures"].append({"source": src.id, "version": ver.version, "reason": b.reason})
                else:
                    b.status, b.reason, b.locator = ref.state, None, ref.locator
                    b.dp_asset_id, b.dp_asset_version_id = ref.asset_id, ref.asset_version_id
                    rep["available"] += 1
            except Exception as e:  # noqa: BLE001 — one version's failure must not stop the run
                b.status, b.reason = "failed", f"{getattr(e, 'code', type(e).__name__)}: {e}"[:300]
                rep["failed"] += 1
                rep["failures"].append({"source": src.id, "version": ver.version, "reason": b.reason})
        b.last_synced_at = now_iso()
        try:
            ka.repo.put_binding(b)
        except ValueError as e:
            # two SourceVersions share (source, version) with different bytes: the binding key is taken. Reported, never papered over —
            # the version stays unbound and the Dashboard's legacy count shows it (research-03 R14 rehearsal finding, 2026-10-09).
            rep["conflicts"] += 1
            if b.status == "available":
                rep["available"] -= 1
            elif b.status == "failed":
                rep["failed"] -= 1
                rep["failures"] = [f for f in rep["failures"] if not (f["source"] == src.id and f["version"] == ver.version)]
            rep["conflict_versions"].append({"source": src.id, "version": ver.version, "source_version_id": ver.id, "reason": str(e)[:200]})
    if publish_active and apply:
        for v in ka.repo.nuggets.where(lambda n: n.status == NuggetStatus.ACTIVE):
            art = ka.derived.publish(v.ref, event="backfill")
            if art is not None:
                rep["published"] += 1
        for _ in range(int(config.get("KA_DP_RETRIES")) + 1):
            if not ka.outbox.due():
                break
            ka.outbox.process_once(by="backfill")
        rep["outbox"] = ka.outbox.status()["by_state"]
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--storage", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--publish-active", action="store_true")
    a = ap.parse_args(argv)
    ka = KnowledgeAcquisition(Path(a.storage), provider=StubLLMProvider(), auto_propose_graph_changes=False, start_workers=False)
    if a.apply and ka.physical.name == "local":
        print(f"refusing --apply: the backend is local ({ka.physical_note or 'KA_STORAGE_BACKEND=local'}) — nothing to migrate to", file=sys.stderr)
        return 2
    print(json.dumps(backfill(ka, apply=a.apply, publish_active=a.publish_active), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
# [/block plan-23]
