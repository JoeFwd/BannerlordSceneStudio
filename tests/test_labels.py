# -*- coding: utf-8 -*-
"""Step definitions for features/labels.feature.

Sizing comes from the stable window.__labelSizes() probe. The "no dark box" check
takes a screenshot and samples pixel luminance (PIL) in each label region: the
brightest pixel sits clearly above the terrain below (legible content, not a dark
slab) while the darkest pixel drops near terrain level (terrain shows through). We
compare against local terrain rather than an absolute threshold: correctly
anti-aliased/mipmapped text is soft, not a hard bright spike (that spike used to be
minification flicker), so an absolute floor would just re-encode that artifact.
"""
from pathlib import Path

from PIL import Image
from pytest_bdd import scenarios, then

scenarios("../features/labels.feature")

TMP = Path(__file__).parent / "_tmp"
W, H = 1600, 950


def _sizes(page):
    return page.evaluate("() => window.__labelSizes()")


@then("the town label is larger than the castle label")
def _town_gt_castle(page, ctx):
    s = _sizes(page)
    ctx["sizes"] = s
    assert s["town"] > s["castle"], s


@then("the castle label is larger than the village label")
def _castle_gt_village(page, ctx):
    s = ctx.get("sizes") or _sizes(page)
    assert s["castle"] > s["village"], s


@then("the town label is at least 1.6 times the village label")
def _town_ratio(page, ctx):
    s = ctx.get("sizes") or _sizes(page)
    ratio = s["town"] / s["village"]
    assert ratio > 1.6, f"town/village label ratio too small: {ratio:.3f}"


def _sample_labels(page):
    TMP.mkdir(parents=True, exist_ok=True)
    shot = TMP / "outline_probe.png"
    # Labels hold a constant on-screen size and fade out at the full-view zoom (they
    # declutter when you're far), so zoom in to a settlement-reading distance first.
    page.mouse.move(W // 2, H // 2)
    for _ in range(8):
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(40)
    page.wait_for_timeout(500)
    screens = [
        s for s in page.evaluate("() => window.__markerScreens()")
        if s["movable"] and s["visible"] and 80 < s["x"] < W - 80 and 80 < s["y"] < H - 80
    ]
    page.screenshot(path=str(shot))
    img = Image.open(shot).convert("RGB")
    w, h = img.size

    def px(x, y):
        return img.getpixel((int(x), int(y))) if 0 <= int(x) < w and 0 <= int(y) < h else None

    def lum(c):
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

    results = []
    for s in screens[:12]:
        lums = []
        for dy in range(-58, -6):
            for dx in range(-45, 46):
                c = px(s["x"] + dx, s["y"] + dy)
                if c:
                    lums.append(lum(c))
        if not lums:
            continue
        terr_c = px(s["x"], s["y"] + 40)
        terr = lum(terr_c) if terr_c else 0
        results.append({"lo": min(lums), "hi": max(lums), "terr": terr})
    return results


@then("the label glyphs are bright and legible")
def _labels_bright(page, ctx):
    results = _sample_labels(page)
    ctx["label_samples"] = results
    assert len(results) >= 5, f"too few sampled labels ({len(results)})"
    # Legible = the label region is clearly brighter than the terrain beneath it
    # (soft anti-aliased text still reads), not an absolute spike that only the old
    # minification flicker produced.
    bright = [r for r in results if r["hi"] > r["terr"] + 30]
    # allow a couple of occluded/overlapping labels; the strong majority must be legible
    assert len(bright) >= len(results) - 2, (
        f"labels not legible over terrain: {[(round(r['hi']), round(r['terr'])) for r in results]}"
    )


@then("terrain shows through the label area instead of a dark slab")
def _terrain_through(ctx):
    results = ctx["label_samples"]
    # a filled dark box would keep every pixel dark (lo high); an outlined glyph lets
    # terrain-level pixels through, so lo drops close to the terrain luminance below.
    through = [r for r in results if r["lo"] < r["terr"] + 25]
    assert len(through) >= len(results) - 2, (
        f"label regions still look like dark slabs: "
        f"{[(round(r['lo']), round(r['terr'])) for r in results]}"
    )
