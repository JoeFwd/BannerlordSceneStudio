# -*- coding: utf-8 -*-
"""Shared fixtures + the common Background step for the regression suite.

The suite boots its OWN uvicorn instance (tests/_serve.py) on a free ephemeral
port against the real, read-only campaign scene, so it never interferes with the
user's live editing session on port 8770. All test traffic hits read-only or
in-memory-only endpoints (/api/entities, /api/info, /api/reset_moves,
/api/move_entity). It NEVER calls /api/save or /api/save_entities.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright
from pytest_bdd import given

TOOL_ROOT = Path(__file__).resolve().parents[1]
SERVE = TOOL_ROOT / "tests" / "_serve.py"
SCENE = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\DellarteDellaGuerraMap\SceneObj\Main_map"
)
VIEWPORT = {"width": 1600, "height": 950}
TMP = TOOL_ROOT / "tests" / "_tmp"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def server_url():
    """Start a private test server on a free port; tear it down at session end."""
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, str(SERVE), SCENE, str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("test server exited early:\n" + (proc.stdout.read() or ""))
        try:
            with urlopen(url + "/api/info", timeout=3) as r:
                info = json.load(r)
            if info.get("navmesh", {}).get("faces", 0) > 0:
                break
        except Exception:
            time.sleep(0.8)
    else:
        proc.terminate()
        raise RuntimeError("test server never became ready with a loaded scene")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def _playwright():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(_playwright):
    b = _playwright.chromium.launch()
    yield b
    b.close()


@pytest.fixture
def page(browser, server_url):
    """Fresh page per scenario. Clears staged moves first (in-memory only) so each
    scenario starts from a clean placement state, and fails on any JS error."""
    context = browser.new_context(viewport=VIEWPORT)
    pg = context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    # in-memory-only reset of staged moves; safe, never writes to disk
    pg.request.post(server_url + "/api/reset_moves", data="")
    pg.goto(server_url + "/", wait_until="networkidle")
    pg.wait_for_function(
        "() => window.__markerScreens && window.__markerScreens().length > 0",
        timeout=45000,
    )
    pg.wait_for_timeout(300)
    yield pg
    fatal = [e for e in errors if "favicon" not in e.lower()]
    context.close()
    assert not fatal, f"page raised JS errors: {fatal}"


@pytest.fixture
def ctx() -> dict:
    """Mutable per-scenario context to carry values between When/Then steps."""
    return {}


# --- shared Background step (used by every feature) --------------------------
@given("the studio is loaded with the campaign scene")
def _loaded(page):
    # click empty canvas to focus the document body (not an input) and settle
    page.mouse.click(960, 475)
    page.wait_for_timeout(120)
    return page
