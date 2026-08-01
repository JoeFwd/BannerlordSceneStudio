import * as THREE from 'three';

// Bannerlord is Z-up; three.js is Y-up. World (x,y,z) -> three (x, z, -y).
export const W2T = (x, y, z) => [x, z, -y];

// Shared raycasting helpers (navmesh hover/select + entity picking).
export const ray = new THREE.Raycaster();
export const mouse = new THREE.Vector2();

// Mutable shared state lives on one object so feature modules can reassign
// fields (ES module bindings are read-only for importers). Values here match
// the original inline-script defaults exactly.
export const store = {
  panRefDist: 800,   // pan speed reference (frozen full-view distance, not live zoom)

  terrainMesh: null, navMesh: null, navEdges: null,
  faces: [], triToFace: [], selection: new Set(),
  colorAttr: null,

  // ---- settlement placement layer ----
  entGroup: null, markerMeshes: [], labelSprites: [], waterLevel: 10.0,
  markerDrag: false, dragEnt: null, dragMoved: false, overMarker: false, lastMove: 0,
  movedCount: 0, selectedEnt: null, labelsOn: true,

  isCampaign: false, colorMode: 'terrain',
};
