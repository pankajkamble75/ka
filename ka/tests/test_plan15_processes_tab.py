"""plan-15 (research-02 R7; product test PT7 via the live flow) — Processes is a top-level console tab pointing at the plan-06
profile view; the original tabs and Browse by scope's Processes mode stay."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from ka.api import PREFIX, create_app, set_ka

JS = Path("ka/console/app.js").read_text(encoding="utf-8")


def test_P1_the_console_declares_the_processes_tab_and_route_and_keeps_the_browse_mode():
    assert '4 · Processes' in JS and "href=\"#/processes\"" in JS
    assert re.search(r"\[/\^#\\/processes\(\?:\\\?\(\.\*\)\)\?\$/, processesView\]", JS), "route table entry for #/processes"
    assert "'#/processes': '4 · Processes'" in JS                       # tabOf knows the tab
    assert "mode === 'processes'" in JS and "await processesList(sel);" in JS   # the Browse mode stays


def test_P3_detail_pages_reached_from_the_tab_return_to_it():
    assert "subject" in JS.split("const detail = ")[1].split("\n")[0]       # subject pages are detail pages
    assert 'crumbs"><a href="#/processes">Processes</a>' in JS              # the profile crumb points at the tab


def test_N1_the_original_tabs_and_images_are_all_present_in_order():
    labels = ["1 · Add knowledge", "2 · Knowledge nuggets", "3 · Browse by scope", "4 · Processes", "5 · Dashboard", "6 · Images"]
    nav = JS.split('<a href="#/add"')[1].split("<h4>You</h4>")[0]
    pos = [nav.index(l) for l in labels]
    assert pos == sorted(pos)


def test_N2_an_unknown_scope_filter_renders_an_empty_state_not_an_error(ka):
    c = TestClient(create_app(ka))
    r = c.get(f"{PREFIX}/processes?scope_type=DOMAIN&scope_id=no-such-scope")
    assert r.status_code == 200 and r.json()["processes"] == []
    set_ka(None)
