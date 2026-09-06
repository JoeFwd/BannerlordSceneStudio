import { useStudioStore } from '../state/studioStore';
import { useEntitiesStore } from '../state/entitiesStore';
import type { ColorMode } from '../domain/terrainColors';
import { Legend } from './Legend';
import { SelInfo } from './SelInfo';
import { EntInfo, SelInfoEnt, saveEntLabel } from './EntityInfo';

// The left control panel. Pure presentation + event wiring: every button/field
// dispatches to a store action; no business logic lives here. DOM ids are pinned
// by the E2E suite and must not change.
export function Panel() {
  const s = useStudioStore();
  const e = useEntitiesStore();

  return (
    <div id="panel">
      <h2>Bannerlord Navmesh Studio</h2>

      <label>Scene directory</label>
      <input id="sceneDir" value={s.sceneDir} onChange={(ev) => s.setField('sceneDir', ev.target.value)} />
      <button onClick={() => s.browse()}>Browse&hellip;</button>
      <button className="dim" onClick={() => s.loadScene()}>Load scene</button>

      <div id="stats" style={{ whiteSpace: 'pre-wrap' }}>{s.statsText}</div>

      <label>Colour by</label>
      <select id="colorMode" value={s.colorMode} onChange={(ev) => s.setColorMode(ev.target.value as ColorMode)}>
        <option value="editor">editor colours (Plain / Mountain / Lake / River)</option>
        <option value="terrain">terrain type / face id (g3)</option>
        <option value="island">island (g5)</option>
      </select>
      <Legend />
      <label>
        <input id="rawNavmesh" type="checkbox" checked={s.rawNavmesh} onChange={() => s.toggleRawNavmesh()} />
        Raw mesh: no display lift, front faces only
      </label>
      {s.rawNavmesh && <small>Diagnostic view only; not an emulation of Bannerlord's renderer.</small>}

      <hr style={{ borderColor: '#333' }} />
      <b>Generate from terrain</b>
      <label>Cell size (m)</label>
      <input id="cellSize" value={s.cellSize} onChange={(ev) => s.setField('cellSize', ev.target.value)} />
      <label>Max slope (deg)</label>
      <input id="maxSlope" value={s.maxSlope} onChange={(ev) => s.setField('maxSlope', ev.target.value)} />
      <label>Region min_x,min_y,max_x,max_y (blank = whole map)</label>
      <input id="region" placeholder="900,1000,1100,1200" value={s.region} onChange={(ev) => s.setField('region', ev.target.value)} />
      <button onClick={() => s.generate(true)}>Generate (replace)</button>
      <button className="dim" onClick={() => s.generate(false)}>Append</button>

      <hr style={{ borderColor: '#333' }} />
      <b>Selection</b> <span style={{ color: '#777' }}>(click face; shift = multi)</span>
      <SelInfo />
      <label>Face id / terrain type (g3)</label>
      <input id="faceId" value={s.faceId} onChange={(ev) => s.setField('faceId', ev.target.value)} />
      <label>Island (g5)</label>
      <input id="group" value={s.group} onChange={(ev) => s.setField('group', ev.target.value)} />
      <button onClick={() => s.applyAttrs()}>Apply to selection</button>
      <button className="warn" onClick={() => s.deleteSelection()}>Delete selection</button>

      <hr style={{ borderColor: '#333' }} />
      <button onClick={() => s.saveMesh()}>Save navmesh.bin</button>
      <button className="dim" onClick={() => s.toggleTerrain()}>Toggle terrain</button>

      <hr style={{ borderColor: '#333' }} />
      <b>Settlements</b> <span style={{ color: '#777' }}>(drag movable; click to select)</span>
      <button className="dim" onClick={() => e.toggleVisible()}>Show / hide</button>
      <button className="dim" onClick={() => e.toggleLabels()}>Labels</button>
      <div id="entlegend">
        <div className="leg"><span className="sw" style={{ background: '#39d353' }} />zone on land (movable)</div>
        <div className="leg"><span className="sw" style={{ background: '#e6a23c' }} />zone partly on land (ok)</div>
        <div className="leg"><span className="sw" style={{ background: '#e5484d' }} />zone in water (movable)</div>
        <div className="leg"><span className="sw" style={{ background: '#6f7d9c' }} />reference (locked)</div>
        <div className="leg">&#9650; town &nbsp; &#9724; castle &nbsp; &#9679; village</div>
      </div>
      <EntInfo />
      <button id="saveEntBtn" onClick={() => e.saveEntities()}>{saveEntLabel(e.movedCount)}</button>
      <button className="dim" onClick={() => e.resetMoves()}>Reset moves</button>

      <label>Footprint radius — town / castle (world units)</label>
      <div style={{ display: 'flex', gap: 4 }}>
        <input id="townR" style={{ width: '50%' }} placeholder="town" value={e.townR} onChange={(ev) => e.setField('townR', ev.target.value)} />
        <input id="castleR" style={{ width: '50%' }} placeholder="castle" value={e.castleR} onChange={(ev) => e.setField('castleR', ev.target.value)} />
      </div>
      <button className="dim" onClick={() => e.saveTypeRadius()}>Set type radius</button>

      <SelInfoEnt />
      <label>Selected settlement custom radius (blank = use type)</label>
      <input id="customR" placeholder="custom radius" value={e.customR} onChange={(ev) => e.setField('customR', ev.target.value)} />
      <button className="dim" onClick={() => e.saveCustomRadius()}>Apply custom radius</button>

      <div id="msg" style={{ marginTop: 8, color: '#8fb7ff' }}>{s.msg}</div>
    </div>
  );
}
