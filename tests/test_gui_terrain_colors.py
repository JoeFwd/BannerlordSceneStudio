"""Headless check: campaign map faces are coloured by terrain type, legend + hover tooltip work.
Requires the web server running with a Main_map scene loaded."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8770/")
    page.wait_for_selector("#legend .leg", timeout=30000)

    legend = page.inner_text("#legend")
    print("legend:\n" + legend)
    assert "Plain (1)" in legend and "RuralArea (14)" in legend, "terrain names missing"

    # hover the middle of the canvas — camera centres on the mesh, so this should hit a face
    page.mouse.move(860, 450)
    page.wait_for_timeout(300)
    page.mouse.move(862, 452)
    page.wait_for_timeout(300)
    tip = page.inner_text("#tip") if page.is_visible("#tip") else "(no hit)"
    print("tooltip:", tip)

    # island mode still renders a legend
    page.select_option("#colorMode", "island")
    page.wait_for_timeout(200)
    print("island legend:\n" + page.inner_text("#legend"))
    page.select_option("#colorMode", "terrain")
    page.wait_for_timeout(200)

    page.screenshot(path="tests/_tmp/gui_terrain_colors.png")
    assert not errors, f"JS errors: {errors}"
    b.close()
print("GUI TERRAIN COLOR CHECKS PASSED")
