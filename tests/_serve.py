"""Standalone launcher for the regression test server.

Boots its OWN uvicorn instance (default port 8771) against the real, read-only
campaign scene so the suite never touches the user's live session on 8770.

Usage:
    python tests/_serve.py "<scene_dir>" [port]

This deliberately does NOT modify server/web.py's own __main__ port. It reuses
web.py's `app` and loads the scene into shared state before serving.
"""
from __future__ import annotations

import sys
from pathlib import Path

# tool root (parent of tests/) must be importable so `import server.*` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

import server.state as state
from server.web import app

DEFAULT_SCENE = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\DellarteDellaGuerraMap\SceneObj\Main_map"
)


def main() -> None:
    scene = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCENE
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8771
    state.load_scene(scene)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
