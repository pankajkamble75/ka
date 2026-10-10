# [block plan-33]
"""Write KA's service-facing OpenAPI (research-05 R11): the `/v1` surface AgentX and Knowledge Worker call, plus `/healthz`, generated from the
app itself so it cannot drift silently (`ka/tests/test_plan33_service.py` fails when the file is stale).

    .venv/bin/python tools/export_openapi.py            # writes docs/integration/openapi-v1.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "integration" / "openapi-v1.json"


def service_openapi() -> dict:
    from ka.api import PREFIX, create_app
    from ka.llm import StubLLMProvider
    from ka.service import KnowledgeAcquisition
    ka = KnowledgeAcquisition(Path(tempfile.mkdtemp(prefix="ka-openapi-")), provider=StubLLMProvider(), start_workers=False)
    spec = create_app(ka).openapi()
    keep = {p: v for p, v in spec["paths"].items() if p.startswith(f"{PREFIX}/v1/") or p.endswith("/healthz")}
    spec = {**spec, "paths": dict(sorted(keep.items())), "info": {**spec["info"], "title": "Knowledge Acquisition — service API (v1)"}}
    used = json.dumps(spec["paths"])
    comps = spec.get("components", {}).get("schemas", {})
    spec["components"] = {"schemas": {k: v for k, v in sorted(comps.items()) if f"#/components/schemas/{k}" in used or k in ("HTTPValidationError", "ValidationError")}}
    return spec


def render() -> str:
    return json.dumps(service_openapi(), indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(ROOT)} ({len(json.loads(OUT.read_text())['paths'])} paths)")
# [/block plan-33]
