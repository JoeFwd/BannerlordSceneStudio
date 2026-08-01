import * as THREE from 'three';
import { scene, camera, renderer, controls } from './scene.js';
import { api, msg, tip } from './api.js';
import { store, W2T, ray, mouse } from './store.js';

const MAX_ANISO = renderer.capabilities.getMaxAnisotropy();

// ---- settlement placement layer ----
const MARK_LIFT = 2.0;
const C_LAND = 0x39d353, C_PARTIAL = 0xe6a23c, C_WATER = 0xe5484d, C_REF = 0x6f7d9c;
// Distinct symbol per settlement type (colour still encodes land/water/locked).
const geoTown    = new THREE.ConeGeometry(2.6, 5.4, 4);        // 4-sided spire
const geoCastle  = new THREE.CylinderGeometry(1.7, 2.4, 4.6, 6); // keep/tower
const geoVillage = new THREE.SphereGeometry(1.7, 12, 8);
const geoUnknown = new THREE.SphereGeometry(1.4, 10, 8);
const geoForType = t => t === 'town' ? geoTown : t === 'castle' ? geoCastle
  : t === 'village' ? geoVillage : geoUnknown;
const FP_COL = { town: 0x2d6cdf, castle: 0xd08a2d };
// Label text size by type: towns much larger, castles medium, villages baseline.
const LABEL_SCALE = { town: 1.9, castle: 1.35, village: 1.0 };

function updateEntInfo(extra) {
  const el = document.getElementById('entinfo');
  if (!store.markerMeshes.length) { el.textContent = 'no settlements'; return; }
  const mv = store.markerMeshes.filter(m => m.userData.ent.movable);
  const wet = mv.filter(m => !m.userData.ent.on_land).length;
  const part = mv.filter(m => { const f = m.userData.ent.land_fraction;
    return f != null && f > 0 && f < 0.999; }).length;
  el.textContent = `${mv.length} movable · ${wet} in water · ${part} part-land · ${store.movedCount} moved`
    + (extra ? `\n${extra}` : '');
  document.getElementById('saveEntBtn').textContent =
    store.movedCount ? `Save placements (${store.movedCount})` : 'Save placements';
}

// Human word for a settlement's zone verdict.
function zoneWord(s) {
  const f = s.land_fraction;
  if (f == null) return s.on_land ? 'land' : 'WATER';
  if (f >= 0.999) return 'land';
  return f > 0 ? `part land ${Math.round(f * 100)}%` : 'WATER';
}

// Zone-based verdict: green = fully on land, amber = zone partly on land (valid,
// e.g. a coastal/riverside settlement), red = zone entirely in water (invalid).
function markerColor(s) {
  if (!s.movable) return C_REF;
  const f = s.land_fraction;
  if (f == null) return s.on_land ? C_LAND : C_WATER;
  if (f >= 0.999) return C_LAND;
  return f > 0 ? C_PARTIAL : C_WATER;
}

const SS = 2;   // supersample the text canvas so minified/mipmapped glyphs stay crisp
function makeLabel(text, mult = 1) {
  const font = Math.round(26 * mult * SS), pad = Math.round(7 * mult * SS);  // pad gives the text breathing room
  const c = document.createElement('canvas'), ctx = c.getContext('2d');
  ctx.font = `${font}px sans-serif`;
  c.width = Math.ceil(ctx.measureText(text).width) + pad * 2;
  c.height = font + pad * 2;
  ctx.font = `${font}px sans-serif`;
  ctx.textBaseline = 'middle';
  const tx = pad, ty = c.height / 2 + 1;
  ctx.fillStyle = '#ffe9c9'; ctx.fillText(text, tx, ty);   // plain flat text, no outline/glow
  // Default mipmapping (LinearMipmapLinear) + anisotropy: minified text averages
  // smoothly and stably instead of flickering bright/faint as the camera shifts.
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = MAX_ANISO;
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, depthTest: false, transparent: true, opacity: LABEL_OPACITY }));
  // Constant on-screen size (set every frame in tickLabels): the texture is always
  // minified by the same factor, so glyph brightness never swims as you zoom/move.
  // Remember the on-screen target height (px) and the aspect ratio to rebuild scale.
  spr.userData.onPx = ONSCREEN_PX * mult;
  spr.userData.aspect = c.width / c.height;
  spr.position.set(0, 6 * mult, 0);   // lift larger labels clear of the marker
  return spr;
}

// Labels hold a constant ON-SCREEN size instead of a fixed world size. A fixed
// world-size label shrinks/grows with zoom, so the GPU minifies it by an
// ever-changing factor and its glyph brightness swims (the "flicker / whiter on
// approach" bug). Locking the on-screen size keeps the minification factor constant,
// so brightness is stable. Distant labels then fade out so a zoomed-out view isn't a
// wall of same-size names.
const ONSCREEN_PX = 15;         // village on-screen glyph height (px); town/castle scale up
const LABEL_OPACITY = 0.82;     // slightly transparent, per request
const FADE_NEAR = 0.30;         // full opacity when closer than 30% of the full-view distance
const FADE_FAR = 0.58;          // faded out beyond 58% (declutters the zoomed-out view)
function tickLabels() {
  if (!store.labelSprites.length) return;
  const ref = store.panRefDist || 0;
  const near = ref * FADE_NEAR, far = ref * FADE_FAR;
  const wppUnit = 2 * Math.tan(camera.fov * Math.PI / 360) / innerHeight;  // world units per screen px, per unit distance
  for (const spr of store.labelSprites) {
    const p = spr.parent;
    if (!p) continue;
    const d = camera.position.distanceTo(p.position);
    const h = spr.userData.onPx * d * wppUnit;   // world height that projects to a fixed px height
    spr.scale.set(h * spr.userData.aspect, h, 1);
    const fade = !ref ? 1 : d <= near ? 1 : d >= far ? 0 : (far - d) / (far - near);
    spr.material.opacity = LABEL_OPACITY * fade;
    spr.visible = store.labelsOn && fade > 0.02;
  }
}

function makeFootprint(radius, type) {
  const col = FP_COL[type] ?? 0x888888;
  const disc = new THREE.Mesh(new THREE.CircleGeometry(radius, 48),
    new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.16,
      side: THREE.DoubleSide, depthWrite: false }));
  const pts = [];
  for (let i = 0; i <= 64; i++) {
    const a = i / 64 * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0));
  }
  const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.8 }));
  const g = new THREE.Group();
  g.add(disc); g.add(ring);
  g.rotation.x = -Math.PI / 2;      // CircleGeometry lies in XY -> lay flat in XZ
  g.position.set(0, -MARK_LIFT, 0); // sit on the ground under the lifted marker
  return g;
}

async function drawEntities() {
  let data;
  try { data = await api('/api/entities'); } catch { return; }
  if (store.entGroup) { scene.remove(store.entGroup); store.entGroup = null; }
  store.markerMeshes = []; store.labelSprites = [];
  store.movedCount = data.moved || 0; store.waterLevel = data.water_level ?? 10.0;
  const tr = data.type_radius || {};
  if (tr.town != null) document.getElementById('townR').value = tr.town;
  if (tr.castle != null) document.getElementById('castleR').value = tr.castle;
  store.entGroup = new THREE.Group();
  for (const s of data.settlements) {
    const m = new THREE.Mesh(geoForType(s.type),
      new THREE.MeshBasicMaterial({ color: markerColor(s) }));
    const [X, Y, Z] = W2T(s.x, s.y, Math.max(s.height, store.waterLevel) + MARK_LIFT);
    m.position.set(X, Y, Z);
    m.userData.ent = s;
    if (s.movable) {
      if (s.radius) m.add(makeFootprint(s.radius, s.type));
      const lbl = makeLabel(s.name, LABEL_SCALE[s.type] ?? 1); lbl.visible = store.labelsOn;
      m.add(lbl); store.labelSprites.push(lbl);
    }
    store.markerMeshes.push(m); store.entGroup.add(m);
  }
  scene.add(store.entGroup);
  updateEntInfo();
  if (store.selectedEnt) {
    const still = data.settlements.find(s => s.id === store.selectedEnt.id);
    store.selectedEnt = still || null;
    if (store.selectedEnt) showSelectedEnt(store.selectedEnt); else clearSelectedEnt();
  }
  // Debug helper (also handy in the console): project markers to screen px.
  window.__markerScreens = () => store.markerMeshes.map(m => {
    const v = m.position.clone().project(camera);
    return { id: m.userData.ent.id, movable: m.userData.ent.movable,
      on_land: m.userData.ent.on_land, land_fraction: m.userData.ent.land_fraction,
      color: '#' + m.material.color.getHexString(), visible: v.z < 1,
      x: (v.x * 0.5 + 0.5) * innerWidth, y: (-v.y * 0.5 + 0.5) * innerHeight };
  });
  window.__labelSizes = () => {
    const acc = {};
    for (const m of store.markerMeshes) {
      const t = m.userData.ent.type, lbl = m.children.find(c => c.isSprite);
      if (!m.userData.ent.movable || !lbl) continue;
      (acc[t] = acc[t] || []).push(lbl.scale.y);
    }
    const out = {};
    for (const t in acc) out[t] = acc[t].reduce((a, b) => a + b, 0) / acc[t].length;
    return out;   // avg label world-height per type
  };
  window.__entStats = () => {
    const geo = { cone: 0, cylinder: 0, sphere: 0 };
    let rings = 0;
    for (const m of store.markerMeshes) {
      const g = m.geometry.type;
      if (g === 'ConeGeometry') geo.cone++;
      else if (g === 'CylinderGeometry') geo.cylinder++;
      else geo.sphere++;
      if (m.children.some(c => c.isGroup)) rings++;
    }
    return { markers: store.markerMeshes.length, labels: store.labelSprites.length,
      footprintRings: rings, shapes: geo, selected: store.selectedEnt && store.selectedEnt.id };
  };
}

function pickMarker(e) {
  if (!store.entGroup || !store.entGroup.visible || !store.markerMeshes.length) return null;
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObjects(store.markerMeshes, false)[0];
  return hit ? hit.object : null;
}

async function sendMove(ent, x, y) {
  try {
    const r = await api('/api/move_entity', { id: ent.id, x, y });
    ent.x = r.x; ent.y = r.y; ent.height = r.height;
    ent.on_land = r.on_land; ent.land_fraction = r.land_fraction;
    if (!ent.moved) { ent.moved = true; store.movedCount++; }
    store.dragEnt && store.dragEnt.userData.ent === ent && store.dragEnt.material.color.setHex(markerColor(ent));
    updateEntInfo(`${ent.name}: ${r.x.toFixed(1)}, ${r.y.toFixed(1)}  (${zoneWord(r)})`);
  } catch {}
}

addEventListener('pointerdown', e => {
  if (e.button !== 0 || e.target !== renderer.domElement) return;
  const m = pickMarker(e);
  if (!m || !m.userData.ent.movable) return;
  store.markerDrag = true; store.dragEnt = m; store.dragMoved = false; controls.enabled = false;
  document.body.style.cursor = 'grabbing';
  e.stopPropagation();
}, true);

addEventListener('pointermove', e => {
  if (store.markerDrag) {
    if (!store.terrainMesh) return;
    mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
    ray.setFromCamera(mouse, camera);
    const hit = ray.intersectObject(store.terrainMesh)[0];
    if (hit) {
      const wx = hit.point.x, wy = -hit.point.z;
      store.dragMoved = true;
      store.dragEnt.position.set(hit.point.x, Math.max(hit.point.y, store.waterLevel) + MARK_LIFT, hit.point.z);
      tip.textContent = `${store.dragEnt.userData.ent.name}  ${wx.toFixed(1)}, ${wy.toFixed(1)}`;
      tip.style.display = 'block';
      tip.style.left = (e.clientX + 14) + 'px'; tip.style.top = (e.clientY + 10) + 'px';
      const now = performance.now();
      if (now - store.lastMove > 70) { store.lastMove = now; sendMove(store.dragEnt.userData.ent, wx, wy); }
    }
    e.stopPropagation();
    return;
  }
  if (e.target !== renderer.domElement) return;
  const m = pickMarker(e);
  if (m) {
    store.overMarker = true;
    const ent = m.userData.ent;
    const flag = ent.movable ? zoneWord(ent) : 'locked';
    tip.textContent = `${ent.name} · ${ent.type || '?'} · ${flag}${ent.moved ? ' · moved' : ''}`;
    tip.style.display = 'block';
    tip.style.left = (e.clientX + 14) + 'px'; tip.style.top = (e.clientY + 10) + 'px';
  } else if (store.overMarker) {
    store.overMarker = false; tip.style.display = 'none';
  }
}, true);

addEventListener('pointerup', e => {
  if (!store.markerDrag) return;
  if (store.dragMoved) {
    const p = store.dragEnt.position;
    sendMove(store.dragEnt.userData.ent, p.x, -p.z);   // final authoritative position
  } else {
    selectEnt(store.dragEnt.userData.ent);             // a click without a drag = select
  }
  store.markerDrag = false; store.dragEnt = null; controls.enabled = true;
  document.body.style.cursor = '';
  e.stopPropagation();
}, true);

// ---- selection + footprint radius ----
function showSelectedEnt(ent) {
  const rad = ent.radius != null ? ent.radius.toFixed(3) : '(no zone)';
  document.getElementById('selinfoEnt').textContent =
    `${ent.name}\n${ent.type || '?'} · radius ${rad}\n`
    + `${ent.x.toFixed(1)}, ${ent.y.toFixed(1)} · ${ent.on_land ? 'land' : 'WATER'}`;
  document.getElementById('customR').value = ent.radius != null ? ent.radius : '';
}
function clearSelectedEnt() {
  document.getElementById('selinfoEnt').textContent = 'no settlement selected';
  document.getElementById('customR').value = '';
}
function selectEnt(ent) {
  store.selectedEnt = ent; showSelectedEnt(ent); msg(`selected ${ent.name}`);
}

function toggleEntities() {
  if (store.entGroup) { store.entGroup.visible = !store.entGroup.visible; if (!store.entGroup.visible) { store.overMarker = false; tip.style.display = 'none'; } }
}
async function resetMoves() {
  await api('/api/reset_moves', {});
  await drawEntities(); msg('moves reset');
}
async function saveEntities() {
  if (!store.movedCount) return msg('no moves to save');
  const r = await api('/api/save_entities', {});
  msg(`saved ${r.changed} settlement(s) · backups: ${(r.backups || []).join(', ')}`);
  await drawEntities();
}
function toggleLabels() {
  store.labelsOn = !store.labelsOn;
  for (const l of store.labelSprites) l.visible = store.labelsOn;
}
async function saveFootprint() {
  const town = parseFloat(document.getElementById('townR').value);
  const castle = parseFloat(document.getElementById('castleR').value);
  const type_radius = {};
  if (town >= 0) type_radius.town = town;
  if (castle >= 0) type_radius.castle = castle;
  if (!Object.keys(type_radius).length) return msg('enter a town/castle radius');
  await api('/api/set_type_radius', { type_radius });
  msg('type radius saved'); await drawEntities();
}
async function saveCustom() {
  if (!store.selectedEnt) return msg('click a settlement to select it first');
  const v = document.getElementById('customR').value.trim();
  const radius = v === '' ? null : parseFloat(v);
  if (v !== '' && !(radius >= 0)) return msg('radius must be a number');
  const r = await api('/api/set_custom_radius', { id: store.selectedEnt.id, radius });
  store.selectedEnt = r;
  msg(`radius for ${r.name}: ${r.radius != null ? r.radius : '(type default)'}`);
  await drawEntities();
}

export {
  drawEntities, toggleEntities, resetMoves, saveEntities, toggleLabels,
  saveFootprint, saveCustom, tickLabels,
};
