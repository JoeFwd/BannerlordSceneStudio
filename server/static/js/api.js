import { store } from './store.js';

export async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) } : undefined);
  if (!r.ok) { const t = await r.text(); msg('ERROR: ' + t); throw new Error(t); }
  return r.json();
}
export const msg = t => document.getElementById('msg').textContent = t;

// Shared hover tooltip element (navmesh hover + entity hover/drag).
export const tip = document.getElementById('tip');

export function showStats(info) {
  const s = info.navmesh;
  let txt = `scene: ${info.scene_dir}\nfaces: ${s.faces}  verts: ${s.vertices}  edges: ${s.edges}`;
  if (info.terrain) txt += `\nterrain: ${info.terrain.world_size_x}x${info.terrain.world_size_y} m`;
  txt += info.dirty ? '\n[UNSAVED CHANGES]' : '';
  document.getElementById('stats').textContent = txt;
  // Campaign map scenes must be named Main_map; g3 is a TerrainType there.
  store.isCampaign = info.scene_dir.replace(/[\\/]+$/, '').split(/[\\/]/).pop().toLowerCase() === 'main_map';
}
