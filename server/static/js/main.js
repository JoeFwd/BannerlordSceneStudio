import { scene, camera, renderer, controls } from './scene.js';
import { store } from './store.js';
import { api, msg, showStats } from './api.js';
import { drawTerrain, buildLegend } from './terrain.js';
import { drawNavmesh, repaint, updateSelInfo } from './navmesh.js';
import {
  drawEntities, toggleEntities, resetMoves, saveEntities, toggleLabels,
  saveFootprint, saveCustom, tickLabels,
} from './entities.js';
import { applyPan, clock } from './pan.js';

window.browseDir = async () => {
  msg('pick a folder in the dialog (check the taskbar)…');
  const r = await api('/api/browse');
  if (!r.path) { msg('folder selection cancelled'); return; }
  document.getElementById('sceneDir').value = r.path;
  await loadScene();
};
const loadScene = async () => {
  msg('loading…');
  const info = await api('/api/load', { scene_dir: document.getElementById('sceneDir').value });
  showStats(info); store.selection.clear(); updateSelInfo();
  await drawTerrain(); await drawNavmesh(); await drawEntities();
  msg('loaded');
};
window.loadScene = loadScene;
window.genMesh = async (replace) => {
  msg('generating…');
  const body = {
    cell_size: parseFloat(document.getElementById('cellSize').value),
    max_slope_deg: parseFloat(document.getElementById('maxSlope').value),
    replace,
  };
  const r = document.getElementById('region').value.trim();
  if (r) {
    const [a, b, c2, d] = r.split(',').map(parseFloat);
    Object.assign(body, { min_x: a, min_y: b, max_x: c2, max_y: d });
  }
  const info = await api('/api/generate', body);
  showStats(info); store.selection.clear(); updateSelInfo();
  await drawNavmesh(); msg('generated');
};
window.applyAttrs = async () => {
  if (!store.selection.size) return msg('nothing selected');
  await api('/api/set_attrs', { indices: [...store.selection],
    face_id: parseInt(document.getElementById('faceId').value),
    group: parseInt(document.getElementById('group').value) });
  await drawNavmesh(); msg('attributes applied'); updateSelInfo();
};
window.deleteSel = async () => {
  if (!store.selection.size) return msg('nothing selected');
  const info = await api('/api/delete_faces', { indices: [...store.selection] });
  store.selection.clear(); showStats(info); updateSelInfo();
  await drawNavmesh(); msg('deleted');
};
window.saveMesh = async () => {
  const r = await api('/api/save', {});
  msg('saved: ' + r.path);
  showStats(await api('/api/info'));
};
window.toggleTerrain = () => { if (store.terrainMesh) store.terrainMesh.visible = !store.terrainMesh.visible; };
window.setColorMode = v => { store.colorMode = v; repaint(); buildLegend(); };

window.toggleEntities = toggleEntities;
window.resetMoves = resetMoves;
window.saveEntities = saveEntities;
window.toggleLabels = toggleLabels;
window.saveFootprint = saveFootprint;
window.saveCustom = saveCustom;

(async () => {
  try {
    const info = await api('/api/info');
    document.getElementById('sceneDir').value = info.scene_dir;
    showStats(info); await drawTerrain(); await drawNavmesh(); await drawEntities();
  } catch { /* no scene preloaded */ }
})();

renderer.setAnimationLoop(() => {
  applyPan(clock.getDelta());
  controls.update();
  tickLabels();
  renderer.render(scene, camera);
});

// Console/debug helper: camera-target position and live zoom distance.
window.__cam = () => ({ tx: controls.target.x, tz: controls.target.z,
  dist: camera.position.distanceTo(controls.target), panRef: store.panRefDist });
