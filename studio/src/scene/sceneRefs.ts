// A tiny registry bridging the live three.js object graph (owned by R3F scene
// components) to the window.__* probes and the pointer-interaction hooks. It holds
// references, never React state — reads are always live.
import type * as THREE from 'three';
import type { OrbitControls } from 'three-stdlib';
import type { Settlement } from '../domain/types';
import { DEFAULT_PAN_REF_DIST } from '../domain/constants';

export interface MarkerRef {
  mesh: THREE.Mesh;
  ent: Settlement;
  label: THREE.Sprite | null;
  footprint: THREE.Group | null;
}

export const sceneRefs: {
  camera: THREE.PerspectiveCamera | null;
  controls: OrbitControls | null;
  navMesh: THREE.Mesh | null;
  terrainMesh: THREE.Mesh | null;
  markers: MarkerRef[];
  panRefDist: number;
} = {
  camera: null,
  controls: null,
  navMesh: null,
  terrainMesh: null,
  markers: [],
  panRefDist: DEFAULT_PAN_REF_DIST,
};
