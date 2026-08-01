import * as THREE from 'three';
import { scene } from './scene.js';
import { api } from './api.js';
import { store, W2T } from './store.js';

async function drawTerrain() {
  const t = await api('/api/terrain?max_dim=256');
  if (store.terrainMesh) { scene.remove(store.terrainMesh); store.terrainMesh = null; }
  if (!t.rows) return;
  const geo = new THREE.PlaneGeometry(t.world_size_x, t.world_size_y, t.cols - 1, t.rows - 1);
  // PlaneGeometry lies in XY; rows follow +y. Rotate to Z-up world then to three-space.
  const pos = geo.attributes.position;
  const cols = t.cols, rows = t.rows;
  const colors = new Float32Array(pos.count * 3);
  let hmin = Infinity, hmax = -Infinity;
  for (const h of t.heights) { if (h < hmin) hmin = h; if (h > hmax) hmax = h; }
  for (let i = 0; i < pos.count; i++) {
    const col = i % cols, row = (i / cols) | 0;
    const wx = col / (cols - 1) * t.world_size_x;
    const wy = row / (rows - 1) * t.world_size_y;
    const h = t.heights[row * cols + col];
    const [X, Y, Z] = W2T(wx, wy, h);
    pos.setXYZ(i, X, Y, Z);
    const f = (h - hmin) / Math.max(1e-6, hmax - hmin);
    colors[i*3] = 0.15 + 0.25*f; colors[i*3+1] = 0.22 + 0.30*f; colors[i*3+2] = 0.15 + 0.20*f;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  store.terrainMesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({
    vertexColors: true, side: THREE.DoubleSide }));
  scene.add(store.terrainMesh);
}

// TaleWorlds.Core.TerrainType — campaign map navmesh face group ids (g3).
const TERRAIN = {
  0:  ['(unset)',           '#777777'], 1:  ['Plain',    '#7bb661'],
  2:  ['Desert',            '#d9c27a'], 3:  ['Snow',     '#eef2f5'],
  4:  ['Forest',            '#2e6b2e'], 5:  ['Steppe',   '#b5b35c'],
  6:  ['Fording',           '#7ec8d4'], 7:  ['Mountain', '#8a8a92'],
  8:  ['Lake',              '#3f7fbf'], 10: ['Water',    '#2c5fa8'],
  11: ['River',             '#4f8fd0'], 13: ['Canyon',   '#a0653b'],
  14: ['RuralArea',         '#e0954f'], 15: ['Swamp',    '#5d7a4c'],
  16: ['Dune',              '#e3cd8f'], 17: ['Bridge',   '#9c7b5a'],
  18: ['CoastalSea',        '#2a4f8f'], 19: ['OpenSea',  '#1c3a70'],
  20: ['Beach',             '#e8d9a0'], 21: ['Cliff',    '#5a5a60'],
  22: ['NonNavigableRiver', '#6fa3c8'], 23: ['LandRestriction', '#b04040'],
  24: ['SeaRestriction',    '#703070'], 25: ['UnderBridge',     '#77808a'],
};

function keyColor(k, out) {
  if (store.colorMode === 'terrain' && store.isCampaign && TERRAIN[k]) { out.set(TERRAIN[k][1]); return; }
  const hue = (((k % 12) + 12) % 12) / 12;
  out.setHSL(0.55 + 0.35 * hue, 0.75, 0.55);
}

function faceColor(i, out) {
  if (store.selection.has(i)) { out.setRGB(1.0, 0.15, 0.75); return; }
  if (!store.faces.face_id) { out.setRGB(0.3, 0.5, 0.8); return; }
  keyColor(store.colorMode === 'island' ? store.faces.group[i] : store.faces.face_id[i], out);
}

function faceLabel(i) {
  const id = store.faces.face_id[i];
  const name = store.isCampaign && TERRAIN[id] ? ` (${TERRAIN[id][0]})` : '';
  return `face #${i} · id ${id}${name} · island ${store.faces.group[i]}`;
}

function buildLegend() {
  const el = document.getElementById('legend');
  if (!store.faces.face_id) { el.innerHTML = ''; return; }
  const vals = store.colorMode === 'island' ? store.faces.group : store.faces.face_id;
  const counts = new Map();
  for (const v of vals) counts.set(v, (counts.get(v) || 0) + 1);
  const c = new THREE.Color();
  el.innerHTML = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24).map(([k, n]) => {
    keyColor(k, c);
    const name = store.colorMode === 'terrain' && store.isCampaign && TERRAIN[k]
      ? `${TERRAIN[k][0]} (${k})` : `${k}`;
    return `<div class="leg"><span class="sw" style="background:#${c.getHexString()}"></span>`
      + `${name} &times; ${n}</div>`;
  }).join('') + (counts.size > 24 ? '<div class="leg">…</div>' : '');
}

export { drawTerrain, keyColor, faceColor, faceLabel, buildLegend };
