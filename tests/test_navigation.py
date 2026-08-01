# -*- coding: utf-8 -*-
"""Step definitions for features/navigation.feature.

Camera state is read exclusively through the stable window.__cam() probe
({tx, tz, dist, panRef}); three.js camera/controls are module-scoped and not
reachable otherwise.
"""
from pytest_bdd import scenarios, when, then, parsers

scenarios("../features/navigation.feature")

PAN_EPS = 1.0        # world units: a real pan moves hundreds; noise is ~0
STILL_EPS = 0.5      # world units: guarded (typing) pan must be ~0


def _cam(page):
    return page.evaluate("() => window.__cam()")


def _target_move(a, b):
    return ((b["tx"] - a["tx"]) ** 2 + (b["tz"] - a["tz"]) ** 2) ** 0.5


def _hold_key(page, key, ms):
    a = _cam(page)
    page.keyboard.down(key)
    page.wait_for_timeout(ms)
    page.keyboard.up(key)
    page.wait_for_timeout(80)
    return _target_move(a, _cam(page))


def _hold_code(page, code, ms):
    """Simulate an AZERTY user: dispatch a physical-position event whose e.key is
    the AZERTY letter but whose e.code is the QWERTY-diamond position the app reads."""
    azerty_key = {"KeyW": "z", "KeyA": "q", "KeyS": "s", "KeyD": "d"}.get(code, "x")
    a = _cam(page)
    page.evaluate(
        "([c, k]) => window.dispatchEvent(new KeyboardEvent('keydown', {code: c, key: k, bubbles: true}))",
        [code, azerty_key],
    )
    page.wait_for_timeout(ms)
    page.evaluate(
        "([c, k]) => window.dispatchEvent(new KeyboardEvent('keyup', {code: c, key: k, bubbles: true}))",
        [code, azerty_key],
    )
    page.wait_for_timeout(80)
    return _target_move(a, _cam(page))


# --- WASD / arrows -----------------------------------------------------------
@when(parsers.parse('I hold the "{key}" key for {ms:d} ms'))
def _hold_named(page, ctx, key, ms):
    ctx["moved"] = _hold_key(page, key, ms)


@when(parsers.parse('I hold the AZERTY physical "{code}" key for {ms:d} ms'))
def _hold_azerty(page, ctx, code, ms):
    ctx["moved"] = _hold_code(page, code, ms)


@then("the camera target moves")
def _camera_moved(ctx):
    assert ctx["moved"] > PAN_EPS, f"camera target barely moved ({ctx['moved']:.3f})"


# --- typing guard ------------------------------------------------------------
@when(parsers.parse('I focus the town-radius input and type "{text}"'))
def _type_in_field(page, ctx, text):
    page.click("#townR")
    page.fill("#townR", "")
    before = _cam(page)
    page.keyboard.type(text, delay=60)
    page.wait_for_timeout(200)
    ctx["field_move"] = _target_move(before, _cam(page))


@then(parsers.parse('the field contains "{text}"'))
def _field_contains(page, text):
    val = page.input_value("#townR")
    assert text in val, f"keys did not reach the input: {val!r}"


@then("the camera target does not move")
def _camera_still(ctx):
    assert ctx["field_move"] < STILL_EPS, (
        f"typing wrongly panned the camera ({ctx['field_move']:.3f})"
    )


# --- zoom-eased-but-floored pan speed ---------------------------------------
# Pinned behaviour: applyPan eases pan speed down with zoom (effDist = liveDist,
# capped at panRefDist when zoomed out) but floors it at panRefDist * 0.25 so a
# deep-zoom pan never crawls. Measured on the live map with the 25% floor the
# deep/full ratio lands ~0.20-0.30, and a moderate zoom pans faster than a deep one.
def _wheel_notches(page, n):
    page.mouse.move(1000, 470)
    for _ in range(n):
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(15)


@when(parsers.parse("I record the pan for an {ms:d} ms hold fully zoomed out"))
def _pan_out(page, ctx, ms):
    page.mouse.click(960, 475)
    ctx["dist_out"] = _cam(page)["dist"]
    ctx["far"] = _hold_key(page, "w", ms)


@when(parsers.parse("I record the pan for an {ms:d} ms hold after zooming in 5 notches"))
def _pan_mid(page, ctx, ms):
    ctx["dist_before_zoom"] = _cam(page)["dist"]
    _wheel_notches(page, 5)
    ctx["dist_after5"] = _cam(page)["dist"]
    ctx["mid"] = _hold_key(page, "w", ms)


@when(parsers.parse("I record the pan for an {ms:d} ms hold after zooming in 25 more notches"))
def _pan_near(page, ctx, ms):
    _wheel_notches(page, 25)
    ctx["dist_near"] = _cam(page)["dist"]
    ctx["near"] = _hold_key(page, "w", ms)


@then("the pan distance shrinks as the zoom deepens")
def _pan_scales(ctx):
    assert ctx["far"] > ctx["mid"] > ctx["near"], (
        f"pan speed did not ease with zoom: far={ctx['far']:.1f} "
        f"mid={ctx['mid']:.1f} near={ctx['near']:.1f}"
    )


@then("the deep-zoom pan is a floored fraction of the zoomed-out pan")
def _pan_floored(ctx):
    ratio = ctx["near"] / ctx["far"] if ctx["far"] else 0.0
    #  - clearly BELOW full-speed (eases with zoom, not the old zoom-independent ~1.0)
    #  - clearly ABOVE the old ~0.16 crawl (floored at 25% of full-view speed)
    assert 0.15 < ratio < 0.40, f"deep-zoom pan ratio out of floored band: {ratio:.3f}"
    assert ctx["near"] > ctx["dist_near"] * 2, (
        f"deep-zoom pan barely moved ({ctx['near']:.1f}) vs dist {ctx['dist_near']:.1f} — crawling"
    )


@then("zooming in 5 notches shrank the camera distance by at least a third")
def _wheel_zoom_shrink(ctx):
    shrink = 1.0 - ctx["dist_after5"] / ctx["dist_before_zoom"]
    assert shrink > 0.33, f"5 wheel notches only shrank distance by {shrink:.3f} (zoomSpeed regressed?)"
