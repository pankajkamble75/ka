# [block plan-29]
"""Check KA's AgentX payloads against AgentX's own contract (research-05 R2, R4): the vendored JSON Schemas in `ka/agentx/schemas/` plus the
rules AgentX enforces in code (ids, versions, relative endpoints, Draft 2020-12 input/output schemas, UI-schema text rules). Used by tests
and by `GET /v1/capabilities?check=1`; needs `jsonschema` (the `dev` extra)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMAS = Path(__file__).parent / "schemas"
CAP_ID = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
UI_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
FORBIDDEN_TEXT = re.compile(r"<\s*/?\s*[a-zA-Z!]|javascript\s*:|data\s*:\s*text/html|vbscript\s*:|\{\{|\$\{", re.I)


def _registry():
    from referencing import Registry, Resource
    reg = Registry()
    for p in SCHEMAS.glob("*.schema.json"):
        reg = reg.with_resource(p.name, Resource.from_contents(json.loads(p.read_text())))
    return reg


def errors(schema_name: str, instance: Any) -> list[str]:
    from jsonschema import Draft202012Validator
    schema = json.loads((SCHEMAS / schema_name).read_text())
    v = Draft202012Validator(schema, registry=_registry())
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in v.iter_errors(instance)]


def _relative(path: str) -> bool:
    return path.startswith("/") and "://" not in path and ".." not in path


def ui_errors(ui: dict[str, Any]) -> list[str]:
    out = errors("UiSchema.schema.json", ui)

    def text(where: str, value: Any, limit: int | None = None) -> None:
        if isinstance(value, str):
            if FORBIDDEN_TEXT.search(value):
                out.append(f"{where}: markup, template or script URL is refused")
            if limit and len(value) > limit:
                out.append(f"{where}: longer than {limit}")
    text("title", ui.get("title"))
    actions = {a.get("id") for a in ui.get("actions", [])}
    for f in ui.get("forms", []):
        if not UI_ID.match(str(f.get("id", ""))):
            out.append(f"form id {f.get('id')!r}")
        if f.get("submit", "submit") != "submit" and f.get("submit") not in actions:
            out.append(f"form {f.get('id')}: submit {f.get('submit')!r} names no action")
        for fl in f.get("fields", []):
            if not str(fl.get("name", "")).isidentifier():
                out.append(f"field name {fl.get('name')!r}")
            text(f"field {fl.get('name')} label", fl.get("label"), 200)
            text(f"field {fl.get('name')} help", fl.get("help"), 500)
            if fl.get("type") in ("select", "multiselect") and not fl.get("options"):
                out.append(f"field {fl.get('name')}: select needs options")
            for o in fl.get("options", []):
                text(f"field {fl.get('name')} option", o.get("label"), 200)
    for v in ui.get("views", []):
        if not UI_ID.match(str(v.get("id", ""))):
            out.append(f"view id {v.get('id')!r}")
    for a in ui.get("actions", []):
        if not UI_ID.match(str(a.get("id", ""))):
            out.append(f"action id {a.get('id')!r}")
        text(f"action {a.get('id')} label", a.get("label"), 200)
        if a.get("kind") == "invoke" and not a.get("capability"):
            out.append(f"action {a.get('id')}: invoke needs capability")
    return out


def descriptor_errors(d: dict[str, Any]) -> list[str]:
    from jsonschema import Draft202012Validator
    out = errors("CapabilityDescriptor.schema.json", d)
    if not CAP_ID.match(str(d.get("id", ""))):
        out.append(f"id {d.get('id')!r} does not match AgentX's pattern")
    if not SEMVER.match(str(d.get("version", ""))):
        out.append(f"version {d.get('version')!r} is not MAJOR.MINOR.PATCH")
    for k in ("health_endpoint",):
        if not _relative(str(d.get(k, "/healthz"))):
            out.append(f"{k} must be relative")
    if not _relative(str((d.get("invocation") or {}).get("endpoint", "/"))):
        out.append("invocation.endpoint must be relative")
    for k in ("input_schema", "output_schema"):
        try:
            Draft202012Validator.check_schema(d.get(k) or {})
        except Exception as e:  # noqa: BLE001
            out.append(f"{k}: {e}")
    if d.get("ui_schema") is not None:
        out += [f"ui_schema: {e}" for e in ui_errors(d["ui_schema"])]
    return out
# [/block plan-29]
