# Regression suite (Gherkin + Playwright)

Characterization tests that PIN the current behaviour of the settlement-placement
map editor (`server/static/index.html`). They are the safety net for refactoring
the front-end into smaller modules.

## What they cover

| Feature file | Scenarios |
|---|---|
| `../features/navigation.feature` | WASD / ZQSD (AZERTY, physical `event.code`) / arrow-key panning; the typing guard; and the zoom-eased-but-floored pan speed + wheel-zoom speed. |
| `../features/settlements.feature` | Zone land-verdict marker colours (green / amber / red / grey-locked); the land/coastal/water mix + `#entinfo` part-land count + `#entlegend` amber row; drag-to-stage-a-move; reference settlements not draggable; per-type marker shapes + footprint rings. |
| `../features/labels.feature` | Per-type label sizing (town > castle > village); outlined labels (bright glyphs, terrain shows through, no dark slab). |

Assertions read the four stable UI probes only — `window.__markerScreens()`,
`window.__labelSizes()`, `window.__entStats()`, `window.__cam()` — plus the DOM
(`#entinfo`, `#entlegend`, `#saveEntBtn`, `#townR`) and screenshot pixels (PIL).

## Safety

- The suite boots **its own** uvicorn server (`tests/_serve.py`) on a **free
  ephemeral port** against the real, read-only campaign scene. It never touches
  the user's live session on port 8770, and tears its own server down at the end.
- It calls **only read-only / in-memory endpoints**: `/api/info`, `/api/entities`,
  `/api/reset_moves`, `/api/move_entity`. It **never** calls `/api/save` or
  `/api/save_entities`, so nothing is ever written to the scene on disk.

## Running

```powershell
# from the tool root: C:\Users\Joe\Desktop\bannerlord-navmesh-studio
pytest -q
```

The session-scoped fixtures start the server + a headless Chromium once and reuse
them across all scenarios; each scenario gets a fresh page and its staged moves
reset first.

## Dependencies

```powershell
pip install pytest pytest-bdd playwright pillow
python -m playwright install chromium
```

(`playwright` and `pillow` already ship with the scratchpad tooling; `pytest-bdd`
is the only extra this suite adds.)

## Scene

Hard-coded, read-only, in `tests/conftest.py`:

```
D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraMap\SceneObj\Main_map
```
