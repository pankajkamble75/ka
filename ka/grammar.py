# [block plan-03]
"""Grammar registry (research-01 R8, KA half): reads Enterprise OS's governed grammar files — `grammar.json`
(`grammar/vN`) and `process_types.json` (`process-types/vN`) — by version string AND sha256 digest, snapshots both, and
fails closed when the files change under the same version string.

KA never defines grammar (EOS `process-typed-graph.md`, Q433). This module only *reads* what EOS owns. When EOS exposes the
same two files behind an endpoint (Q7), that becomes a second source behind the same registry.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ka import config
from ka.json_io import read_json, write_json


class GrammarMismatch(RuntimeError):
    """The files on disk differ from the snapshot under the same version string."""


@dataclass
class GrammarSnapshot:
    grammar_version: str
    type_table_version: str
    grammar_digest: str
    type_table_digest: str
    loaded_at: str
    source_dir: str

    def key(self) -> str:
        return f"{self.grammar_version}|{self.type_table_version}|{self.grammar_digest[:12]}|{self.type_table_digest[:12]}"


@dataclass
class GrammarRegistry:
    dir: Path | None
    snapshot_path: Path
    grammar: dict[str, Any] = field(default_factory=dict)
    types: dict[str, Any] = field(default_factory=dict)
    snapshot: GrammarSnapshot | None = None
    _stale_reason: str | None = None

    # ---- loading ------------------------------------------------------------------------------------

    @classmethod
    def from_config(cls, storage_root: Path) -> "GrammarRegistry":
        raw = config.get("KA_GRAMMAR_DIR")
        if not raw and config.get("KA_ENTERPRISE_OS_ROOT"):
            raw = str(Path(config.get("KA_ENTERPRISE_OS_ROOT")) / "knowledge_worker" / "graph_model")
        reg = cls(dir=Path(raw) if raw else None, snapshot_path=storage_root / "grammar_snapshot.json")
        reg.load()
        return reg

    @property
    def loaded(self) -> bool:
        return bool(self.grammar) and bool(self.types)

    def _read(self) -> tuple[dict, dict, str, str]:
        g_path, t_path = self.dir / "grammar.json", self.dir / "process_types.json"
        g_bytes, t_bytes = g_path.read_bytes(), t_path.read_bytes()
        g, t = json.loads(g_bytes), json.loads(t_bytes)
        if not str(g.get("version", "")).startswith("grammar/"):
            raise GrammarMismatch(f"{g_path}: version {g.get('version')!r} is not a grammar version")
        if not str(t.get("version", "")).startswith("process-types/"):
            raise GrammarMismatch(f"{t_path}: version {t.get('version')!r} is not a process-types version")
        return g, t, hashlib.sha256(g_bytes).hexdigest(), hashlib.sha256(t_bytes).hexdigest()

    def load(self) -> None:
        """Load the files and reconcile with the snapshot. Same versions + different digest → stale (fail closed)."""
        self._stale_reason = None
        prior = GrammarSnapshot(**read_json(self.snapshot_path)) if self.snapshot_path.exists() else None
        if self.dir is None or not (self.dir / "grammar.json").exists():
            self.grammar, self.types, self.snapshot = {}, {}, prior
            return
        g, t, gd, td = self._read()
        from ka.timeutil import now_iso
        current = GrammarSnapshot(g["version"], t["version"], gd, td, now_iso(), str(self.dir))
        if prior and (prior.grammar_version, prior.type_table_version) == (current.grammar_version, current.type_table_version) \
                and (prior.grammar_digest, prior.type_table_digest) != (current.grammar_digest, current.type_table_digest):
            self._stale_reason = (f"grammar files changed under the same version strings ({prior.grammar_version}, "
                                  f"{prior.type_table_version}): digest {prior.grammar_digest[:12]}/{prior.type_table_digest[:12]} → "
                                  f"{gd[:12]}/{td[:12]}; refresh(force=True) to accept")
            self.grammar, self.types, self.snapshot = g, t, prior
            return
        self.grammar, self.types, self.snapshot = g, t, current
        if prior is None or prior.key() != current.key():
            write_json(self.snapshot_path, current.__dict__)

    def is_stale(self) -> bool:
        return self._stale_reason is not None

    def stale_reason(self) -> str | None:
        return self._stale_reason

    def refresh(self, *, force: bool = False) -> GrammarSnapshot | None:
        """Re-read the files. A same-version digest change is refused unless `force`."""
        self.load()
        if self.is_stale():
            if not force:
                raise GrammarMismatch(self._stale_reason or "stale")
            g, t, gd, td = self._read()
            from ka.timeutil import now_iso
            self.snapshot = GrammarSnapshot(g["version"], t["version"], gd, td, now_iso(), str(self.dir))
            self.grammar, self.types, self._stale_reason = g, t, None
            write_json(self.snapshot_path, self.snapshot.__dict__)
        return self.snapshot

    # ---- lookups --------------------------------------------------------------------------------------

    def node_kinds(self) -> list[str]:
        return [k["name"] if isinstance(k, dict) else k for k in self.grammar.get("node_kinds", [])]

    def edge_pairs(self) -> list[dict[str, Any]]:
        out = []
        for group, edges in self.grammar.get("edges", {}).items():
            for e in edges:
                out.append({**e, "group": group})
        return out

    def edge_spec(self, name: str) -> dict[str, Any] | None:
        return next((e for e in self.edge_pairs() if e["name"] == name), None)

    def slots(self) -> list[str]:
        return [s["name"] if isinstance(s, dict) else s for s in self.grammar.get("slots", [])]

    def type_names(self) -> list[str]:
        return list(self.types.get("types", {}))

    def type_grammar(self, name: str) -> dict[str, str] | None:
        t = self.types.get("types", {}).get(name)
        return dict(t["grammar"]) if t else None

    def slot_for_edge(self, edge: str) -> str | None:
        for slot, spec in self.types.get("slot_edges", {}).items():
            for path in spec.get("paths", []):
                if path and path[0].get("edge") == edge and path[0].get("direction", "out") == "out":
                    return slot
        return None

    def versions(self) -> dict[str, str | None]:
        s = self.snapshot
        return {"grammar_version": s.grammar_version if s else None, "type_table_version": s.type_table_version if s else None,
                "grammar_digest": s.grammar_digest if s else None, "type_table_digest": s.type_table_digest if s else None}

    def descriptor(self) -> dict[str, Any]:
        return {"loaded": self.loaded, "stale": self.is_stale(), "stale_reason": self._stale_reason, "source_dir": str(self.dir) if self.dir else None,
                **self.versions(), "node_kinds": self.node_kinds(), "slots": self.slots(), "types": self.type_names(),
                "edges": [{"name": e["name"], "inverse": e.get("inverse"), "from": e.get("from"), "to": e.get("to"), "group": e["group"]} for e in self.edge_pairs()],
                "type_grammar": {n: self.type_grammar(n) for n in self.type_names()}}
# [/block plan-03]
