import * as THREE from 'three';
import { scene, camera, controls, renderer } from './scene.js';
import { tip, api } from './api.js';
import { store, W2T, ray, mouse } from './store.js';
import { faceColor, faceLabel, buildLegend } from './terrain.js';

async function drawNavmesh() {
  const m = await api('/api/mesh');
  store.faces = m;
  if (store.navMesh) { scene.remove(store.navMesh); store.navMesh = null; }
  if (store.navEdges) { scene.remove(store.navEdges); store.navEdges = null; }
  store.triToFace = [];
  const tris = [];
  for (let fi = 0; fi < m.faces.length; fi++) {
    const ids = m.faces[fi];
    for (let k = 2; k < ids.length; k++) {
      tris.push(ids[0], ids[k-1], ids[k]);
      store.triToFace.push(fi);
    }
  }
  const pos = new Float32Array(tris.length * 3);
  const col = new Float32Array(tris.length * 3);
  const c = new THREE.Color();
  for (let i = 0; i < tris.length; i++) {
    const v = tris[i] * 3;
    const [X, Y, Z] = W2T(m.vertices[v], m.vertices[v+1], m.vertices[v+2] + 0.15);
    pos[i*3] = X; pos[i*3+1] = Y; pos[i*3+2] = Z;
    faceColor(store.triToFace[(i / 3) | 0], c);
    col[i*3] = c.r; col[i*3+1] = c.g; col[i*3+2] = c.b;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  store.colorAttr = geo.attributes.color;
  store.navMesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.55, side: THREE.DoubleSide,
    depthWrite: false }));
  scene.add(store.navMesh);
  store.navEdges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 1),
    new THREE.LineBasicMaterial({ color: 0x224466, transparent: true, opacity: 0.6 }));
  scene.add(store.navEdges);
  buildLegend();

  if (m.vertices.length) {
    geo.computeBoundingSphere();
    const bs = geo.boundingSphere;
    controls.target.copy(bs.center);
    camera.position.set(bs.center.x + bs.radius, bs.center.y + bs.radius * 0.9,
                        bs.center.z + bs.radius);
    controls.update();
    store.panRefDist = camera.position.distanceTo(controls.target);   // freeze full-view pan speed
  }
}

function repaint() {
  if (!store.colorAttr) return;
  const c = new THREE.Color();
  for (let t = 0; t < store.triToFace.length; t++) {
    faceColor(store.triToFace[t], c);
    for (let k = 0; k < 3; k++) {
      const i = t * 3 + k;
      store.colorAttr.array[i*3] = c.r; store.colorAttr.array[i*3+1] = c.g; store.colorAttr.array[i*3+2] = c.b;
    }
  }
  store.colorAttr.needsUpdate = true;
}

function updateSelInfo() {
  const el = document.getElementById('selinfo');
  if (!store.selection.size) { el.textContent = 'none'; return; }
  const arr = [...store.selection];
  el.textContent = `${arr.length} face(s): [${arr.slice(0, 12).join(', ')}${arr.length > 12 ? '…' : ''}]`
    + (store.faces.face_id ? `\n${faceLabel(arr[0])}` : '');
}

let lastHover = 0;
renderer.domElement.addEventListener('pointermove', e => {
  if (store.markerDrag || store.overMarker) return;
  if (!store.navMesh || !store.faces.face_id) { tip.style.display = 'none'; return; }
  const now = performance.now();
  if (now - lastHover < 30) return;
  lastHover = now;
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObject(store.navMesh)[0];
  if (!hit) { tip.style.display = 'none'; return; }
  tip.textContent = faceLabel(store.triToFace[hit.faceIndex]);
  tip.style.display = 'block';
  tip.style.left = (e.clientX + 14) + 'px';
  tip.style.top = (e.clientY + 10) + 'px';
});
let downAt = null;
renderer.domElement.addEventListener('pointerdown', e => downAt = [e.clientX, e.clientY]);
renderer.domElement.addEventListener('pointerup', e => {
  if (store.markerDrag) return;
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4 || !store.navMesh) return;
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObject(store.navMesh)[0];
  if (!hit) { if (!e.shiftKey) { store.selection.clear(); repaint(); updateSelInfo(); } return; }
  const fi = store.triToFace[hit.faceIndex];
  if (!e.shiftKey) store.selection.clear();
  store.selection.has(fi) ? store.selection.delete(fi) : store.selection.add(fi);
  repaint(); updateSelInfo();
});

export { drawNavmesh, repaint, updateSelInfo };
