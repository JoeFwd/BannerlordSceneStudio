// Imperative three.js construction, ported line-for-line from the original inline
// scripts. Kept out of the React components so the pixel-exact geometry/label/
// footprint code lives in one place and the components stay declarative. All the
// maths (colours, coords, sizing) comes from the pure domain/ modules.
import * as THREE from 'three';
import type { MeshResponse, Settlement, TerrainResponse } from '../domain/types';
import { W2T } from '../domain/coords';
import {
  MARK_LIFT, NAVMESH_LIFT, GEO, FP_COL, FP_FALLBACK, LABEL_SCALE,
  LABEL_OPACITY, ONSCREEN_PX, SS, LABEL_FILL,
} from '../domain/constants';
import { markerColor } from '../domain/markerColor';
import { faceColor, type FaceColorContext } from '../domain/terrainColors';
import type { MarkerRef } from './sceneRefs';

// ---- terrain ---------------------------------------------------------------
export function buildTerrainMesh(t: TerrainResponse): THREE.Mesh | null {
  if (!t.rows || !t.cols || !t.heights) return null;
  const geo = new THREE.PlaneGeometry(t.world_size_x, t.world_size_y, t.cols - 1, t.rows - 1);
  const pos = geo.attributes.position;
  const cols = t.cols, rows = t.rows;
  const colors = new Float32Array(pos.count * 3);
  let hmin = Infinity, hmax = -Infinity;
  for (const h of t.heights) { if (h < hmin) hmin = h; if (h > hmax) hmax = h; }
  for (let i = 0; i < pos.count; i++) {
    const col = i % cols, row = (i / cols) | 0;
    const wx = (col / (cols - 1)) * t.world_size_x!;
    const wy = (row / (rows - 1)) * t.world_size_y!;
    const h = t.heights[row * cols + col];
    const [X, Y, Z] = W2T(wx, wy, h);
    pos.setXYZ(i, X, Y, Z);
    const f = (h - hmin) / Math.max(1e-6, hmax - hmin);
    colors[i * 3] = 0.15 + 0.25 * f;
    colors[i * 3 + 1] = 0.22 + 0.30 * f;
    colors[i * 3 + 2] = 0.15 + 0.20 * f;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));
}

// ---- navmesh ---------------------------------------------------------------
export interface BuiltNavmesh {
  group: THREE.Group;         // navMesh + edges, added to the scene together
  navMesh: THREE.Mesh;        // the pickable fan-triangulated surface
  colorAttr: THREE.BufferAttribute;
  triToFace: number[];        // triangle index -> source face index
  boundingSphere: THREE.Sphere | null;
}

function ctxFrom(mesh: MeshResponse, selection: Set<number>, colorMode: FaceColorContext['colorMode'], isCampaign: boolean): FaceColorContext {
  return { colorMode, isCampaign, faceId: mesh.face_id, group: mesh.group, selection };
}

export function buildNavmesh(
  mesh: MeshResponse, selection: Set<number>, colorMode: FaceColorContext['colorMode'], isCampaign: boolean,
): BuiltNavmesh {
  const triToFace: number[] = [];
  const tris: number[] = [];
  for (let fi = 0; fi < mesh.faces.length; fi++) {
    const ids = mesh.faces[fi];
    for (let k = 2; k < ids.length; k++) { tris.push(ids[0], ids[k - 1], ids[k]); triToFace.push(fi); }
  }
  const pos = new Float32Array(tris.length * 3);
  const col = new Float32Array(tris.length * 3);
  const ctx = ctxFrom(mesh, selection, colorMode, isCampaign);
  for (let i = 0; i < tris.length; i++) {
    const v = tris[i] * 3;
    const [X, Y, Z] = W2T(mesh.vertices[v], mesh.vertices[v + 1], mesh.vertices[v + 2] + NAVMESH_LIFT);
    pos[i * 3] = X; pos[i * 3 + 1] = Y; pos[i * 3 + 2] = Z;
    const [r, g, b] = faceColor(triToFace[(i / 3) | 0], ctx);
    col[i * 3] = r; col[i * 3 + 1] = g; col[i * 3 + 2] = b;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const colorAttr = new THREE.BufferAttribute(col, 3);
  geo.setAttribute('color', colorAttr);
  const navMesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }));
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 1),
    new THREE.LineBasicMaterial({ color: 0x224466, transparent: true, opacity: 0.6 }));
  const group = new THREE.Group();
  group.add(navMesh); group.add(edges);
  let boundingSphere: THREE.Sphere | null = null;
  if (mesh.vertices.length) { geo.computeBoundingSphere(); boundingSphere = geo.boundingSphere; }
  return { group, navMesh, colorAttr, triToFace, boundingSphere };
}

export function repaintNavmesh(
  built: BuiltNavmesh, mesh: MeshResponse, selection: Set<number>, colorMode: FaceColorContext['colorMode'], isCampaign: boolean,
): void {
  const ctx = ctxFrom(mesh, selection, colorMode, isCampaign);
  const arr = built.colorAttr.array as Float32Array;
  for (let t = 0; t < built.triToFace.length; t++) {
    const [r, g, b] = faceColor(built.triToFace[t], ctx);
    for (let k = 0; k < 3; k++) {
      const i = t * 3 + k;
      arr[i * 3] = r; arr[i * 3 + 1] = g; arr[i * 3 + 2] = b;
    }
  }
  built.colorAttr.needsUpdate = true;
}

// ---- settlement markers ----------------------------------------------------
const geoTown = new THREE.ConeGeometry(GEO.townCone.radius, GEO.townCone.height, GEO.townCone.radialSegments);
const geoCastle = new THREE.CylinderGeometry(GEO.castleCylinder.radiusTop, GEO.castleCylinder.radiusBottom, GEO.castleCylinder.height, GEO.castleCylinder.radialSegments);
const geoVillage = new THREE.SphereGeometry(GEO.villageSphere.radius, GEO.villageSphere.widthSegments, GEO.villageSphere.heightSegments);
const geoUnknown = new THREE.SphereGeometry(GEO.unknownSphere.radius, GEO.unknownSphere.widthSegments, GEO.unknownSphere.heightSegments);
const geoForType = (t: string) =>
  t === 'town' ? geoTown : t === 'castle' ? geoCastle : t === 'village' ? geoVillage : geoUnknown;

function makeLabel(text: string, anisotropy: number, mult = 1): THREE.Sprite {
  const font = Math.round(26 * mult * SS), pad = Math.round(7 * mult * SS);
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d')!;
  ctx.font = `${font}px sans-serif`;
  c.width = Math.ceil(ctx.measureText(text).width) + pad * 2;
  c.height = font + pad * 2;
  ctx.font = `${font}px sans-serif`;
  ctx.textBaseline = 'middle';
  ctx.fillStyle = LABEL_FILL;
  ctx.fillText(text, pad, c.height / 2 + 1);
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = anisotropy;
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true, opacity: LABEL_OPACITY }));
  spr.userData.onPx = ONSCREEN_PX * mult;
  spr.userData.aspect = c.width / c.height;
  spr.position.set(0, 6 * mult, 0);
  return spr;
}

function makeFootprint(radius: number, type: string): THREE.Group {
  const color = FP_COL[type] ?? FP_FALLBACK;
  const disc = new THREE.Mesh(new THREE.CircleGeometry(radius, 48),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }));
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0));
  }
  const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.8 }));
  const g = new THREE.Group();
  g.add(disc); g.add(ring);
  g.rotation.x = -Math.PI / 2;
  g.position.set(0, -MARK_LIFT, 0);
  return g;
}

export interface BuiltMarkers {
  group: THREE.Group;
  markers: MarkerRef[];
}

export function buildMarkers(settlements: Settlement[], waterLevel: number, labelsOn: boolean, anisotropy: number): BuiltMarkers {
  const group = new THREE.Group();
  const markers: MarkerRef[] = [];
  for (const s of settlements) {
    const mesh = new THREE.Mesh(geoForType(s.type), new THREE.MeshBasicMaterial({ color: markerColor(s) }));
    const [X, Y, Z] = W2T(s.x, s.y, Math.max(s.height, waterLevel) + MARK_LIFT);
    mesh.position.set(X, Y, Z);
    mesh.userData.ent = s;
    let label: THREE.Sprite | null = null;
    let footprint: THREE.Group | null = null;
    if (s.movable) {
      if (s.radius) { footprint = makeFootprint(s.radius, s.type); mesh.add(footprint); }
      label = makeLabel(s.name, anisotropy, LABEL_SCALE[s.type] ?? 1);
      label.visible = labelsOn;
      mesh.add(label);
    }
    group.add(mesh);
    markers.push({ mesh, ent: s, label, footprint });
  }
  return { group, markers };
}
