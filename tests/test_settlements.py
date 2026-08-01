# -*- coding: utf-8 -*-
"""Step definitions for features/settlements.feature.

Uses the stable probes window.__markerScreens() and window.__entStats(), the
#entinfo / #entlegend / #saveEntBtn DOM, and real pointer drags. Only staged
(in-memory) moves are exercised; the suite never clicks Save.
"""
from pytest_bdd import scenarios, when, then, parsers

scenarios("../features/settlements.feature")

GREEN, AMBER, RED, REF = "#39d353", "#e6a23c", "#e5484d", "#6f7d9c"
W, H = 1600, 950


def _markers(page):
    return page.evaluate("() => window.__markerScreens()")


def _expected_colour(f):
    if f is None:
        return None
    if f >= 0.999:
        return GREEN
    return AMBER if f > 0 else RED


def _moved_count(page):
    txt = page.text_content("#entinfo")
    return int(txt.split("·")[-1].strip().split()[0])


# --- colour verdict ----------------------------------------------------------
@then("every movable marker colour matches its land fraction")
def _colours_match(page):
    mv = [m for m in _markers(page) if m["movable"]]
    assert mv, "no movable markers"
    bad = [
        (m["id"], m["land_fraction"], m["color"])
        for m in mv
        if _expected_colour(m["land_fraction"]) and m["color"] != _expected_colour(m["land_fraction"])
    ]
    assert not bad, f"colour/verdict mismatch: {bad[:5]}"


@then("reference settlements are the locked grey colour and are not movable")
def _reference_locked(page):
    refs = [m for m in _markers(page) if not m["movable"]]
    assert refs, "no reference settlements found"
    off = [(m["id"], m["color"]) for m in refs if m["color"] != REF]
    assert not off, f"reference markers not grey/locked: {off[:5]}"


# --- land / coastal / water mix ---------------------------------------------
@then("there are movable markers fully on land")
def _has_green(page):
    assert any(m["movable"] and m["color"] == GREEN for m in _markers(page)), "no fully-land markers"


@then("there are movable markers partly on land")
def _has_amber(page):
    assert any(m["movable"] and m["color"] == AMBER for m in _markers(page)), "no part-land markers"


@then("there are movable markers fully in water")
def _has_red(page):
    assert any(m["movable"] and m["color"] == RED for m in _markers(page)), "no water markers"


@then("the info line reports a part-land count")
def _info_part_land(page):
    info = page.text_content("#entinfo")
    assert "part-land" in info, info


@then(parsers.parse('the legend includes the amber "{label}" row'))
def _legend_amber(page, label):
    leg = page.text_content("#entlegend")
    assert label in leg, leg


# --- drag stages a move ------------------------------------------------------
@when("I drag an on-screen movable land marker across the map")
def _drag_movable(page, ctx):
    assert _moved_count(page) == 0, page.text_content("#entinfo")
    cand = [
        m for m in _markers(page)
        if m["movable"] and m["color"] == GREEN and m["visible"]
        and 80 < m["x"] < W - 80 and 80 < m["y"] < H - 80
    ]
    assert cand, "no on-screen movable land marker to drag"
    m = cand[0]
    sx, sy = round(m["x"]), round(m["y"])
    page.mouse.move(sx, sy)
    page.mouse.down()
    for i in range(1, 6):
        page.mouse.move(sx + 60 * i / 5, sy + 45 * i / 5)
        page.wait_for_timeout(25)
    page.mouse.up()
    page.wait_for_timeout(400)
    ctx["moved_after"] = _moved_count(page)


@then("the moved counter increments")
def _moved_incremented(ctx):
    assert ctx["moved_after"] >= 1, f"drag did not stage a move (moved={ctx['moved_after']})"


@then("the save-placements button shows the pending count")
def _savebtn_count(page):
    assert "Save placements (" in page.text_content("#saveEntBtn"), page.text_content("#saveEntBtn")


# --- reference is not draggable ---------------------------------------------
@when("I try to drag an on-screen reference marker")
def _drag_reference(page, ctx):
    cand = [
        m for m in _markers(page)
        if not m["movable"] and m["visible"] and 80 < m["x"] < W - 80 and 80 < m["y"] < H - 80
    ]
    assert cand, "no on-screen reference marker to try"
    m = cand[0]
    sx, sy = round(m["x"]), round(m["y"])
    page.mouse.move(sx, sy)
    page.mouse.down()
    for i in range(1, 6):
        page.mouse.move(sx + 60 * i / 5, sy + 45 * i / 5)
        page.wait_for_timeout(25)
    page.mouse.up()
    page.wait_for_timeout(300)
    ctx["moved_after"] = _moved_count(page)


@then("no move is staged")
def _no_move(ctx):
    assert ctx["moved_after"] == 0, f"reference marker was wrongly moved (moved={ctx['moved_after']})"


# --- per-type marker shapes --------------------------------------------------
@then("the markers include cones, cylinders and spheres")
def _shapes_present(page, ctx):
    stats = page.evaluate("() => window.__entStats()")
    ctx["stats"] = stats
    s = stats["shapes"]
    assert s["cone"] > 0 and s["cylinder"] > 0 and s["sphere"] > 0, s


@then("movable settlements with a radius have a footprint ring")
def _footprint_rings(page, ctx):
    stats = ctx.get("stats") or page.evaluate("() => window.__entStats()")
    assert stats["footprintRings"] > 0, stats
