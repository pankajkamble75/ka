"""plan-28 (research-04 R14; product test PT10) — the regression gate: everything that existed before the Knowledge Wiki is still there,
verbatim — every pre-wiki API route and method, tabs 1–6 and the pre-wiki console routes, and every pre-wiki test file except the
documented relaxations. 83fe82c is the last pre-wiki commit (plan-24)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ka.api import create_app
from ka.llm import StubLLMProvider
from ka.service import KnowledgeAcquisition

ROOT = Path(__file__).resolve().parents[2]
BASE = "83fe82c"
# the ONE documented relaxation after 83fe82c: plan-26's lint pass removed unused assignments (`g = f(...)` → `f(...)`) in two older test
# files; every changed line in them must be exactly that shape, nothing else
ALLOWED_CHANGED = {"ka/tests/test_plan20_outbox.py", "ka/tests/test_plan24_version_numbering.py"}
ASSIGN = re.compile(r"^-(\s*)[A-Za-z_]\w*\s*=\s*(.+)$")


def _show(path: str) -> str:
    return subprocess.run(["git", "show", f"{BASE}:{path}"], cwd=ROOT, capture_output=True, text=True).stdout


def test_N2_PT10_every_pre_wiki_api_route_is_still_registered_with_its_method(tmp_path):
    old = _show("ka/api.py")
    wanted = set(re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"', old))
    assert len(wanted) > 50
    ka = KnowledgeAcquisition(tmp_path / "s", provider=StubLLMProvider())
    app = create_app(ka)
    have = {(m.lower(), r.path.removeprefix("/api/knowledge-acquisition")) for r in app.routes for m in (getattr(r, "methods", None) or [])}
    missing = sorted(w for w in wanted if w not in have)
    assert not missing, f"pre-wiki routes missing or changed: {missing}"


def test_N2b_PT10_tabs_one_to_six_and_the_pre_wiki_console_routes_are_verbatim():
    old, now = _show("ka/console/app.js"), (ROOT / "ka/console/app.js").read_text()
    labels = re.compile(r"'#/(add|nuggets|browse|processes|dashboard|images)': '[^']+'")
    assert labels.findall(old) == labels.findall(now)
    old_routes = re.search(r"const routes = \[(.*?)\n\];", old, re.S).group(1).strip().splitlines()
    now_routes = re.search(r"const routes = \[(.*?)\n\];", now, re.S).group(1).strip().splitlines()
    it = iter(now_routes)
    assert all(any(r == x for x in it) for r in old_routes), "a pre-wiki console route changed or moved out of order"
    for view in ("dashboard", "addView", "nuggetsView", "browseView", "processesView", "imagesView", "subjectView", "nuggetView", "conflictView", "sourceView", "missionView", "changeView"):
        assert f"async function {view}(" in now


def test_N2c_PT10_pre_wiki_test_files_are_byte_identical_to_the_last_pre_wiki_commit():
    out = subprocess.run(["git", "diff", "--name-only", BASE, "HEAD", "--", "ka/tests"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    changed = {p for p in out if not re.search(r"plan(2[5-9]|[3-9][0-9])", p)} - ALLOWED_CHANGED
    assert not changed, f"pre-wiki test files changed since {BASE}: {sorted(changed)}"
    for path in ALLOWED_CHANGED:
        diff = subprocess.run(["git", "diff", BASE, "HEAD", "--", path], cwd=ROOT, capture_output=True, text=True).stdout
        minus = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        plus = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
        assert len(minus) == len(plus), f"{path}: not a pure assignment cleanup"
        for m, pl in zip(minus, plus):
            mm = ASSIGN.match(m)
            assert mm and pl == "+" + mm.group(1) + mm.group(2), f"{path}: unexpected change {m!r} → {pl!r}"
    tracked = subprocess.run(["git", "status", "--short", "--", "ka/tests"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    dirty = {l.split()[-1] for l in tracked if l.strip() and not re.search(r"plan(2[5-9]|[3-9][0-9])", l)}
    assert not dirty, f"pre-wiki test files modified in the working tree: {sorted(dirty)}"
