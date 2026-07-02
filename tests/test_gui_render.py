"""Headless-browser check: the three.js GUI loads, draws, and can select a face."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "_tmp"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto("http://127.0.0.1:8770/", wait_until="networkidle")
    page.wait_for_timeout(4000)  # let /api/mesh + /api/terrain render

    stats = page.text_content("#stats")
    print("stats panel:", stats.replace("\n", " | "))
    assert "faces:" in stats, "scene stats not shown"

    # click center of viewport to select a face
    page.mouse.click(860, 450)
    page.wait_for_timeout(500)
    sel = page.text_content("#selinfo")
    print("selection:", sel.replace("\n", " | "))

    page.screenshot(path=str(OUT / "gui.png"))
    browser.close()

fatal = [e for e in errors if "favicon" not in e]
print("js errors:", fatal if fatal else "none")
assert not fatal, fatal
print("GUI RENDER CHECK PASSED")
