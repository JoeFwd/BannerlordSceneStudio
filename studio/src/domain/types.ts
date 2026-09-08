// Pure data contracts mirroring the FastAPI backend responses. No framework types.

export type SettlementType = 'town' | 'castle' | 'village' | string;

export interface Settlement {
  id: string;
  name: string;
  type: SettlementType;
  movable: boolean;
  x: number;
  y: number;
  height: number;
  land_fraction: number | null;
  on_land: boolean;
  moved: boolean;
  radius: number | null;
}

export interface EntitiesResponse {
  water_level: number;
  type_radius: { town?: number | null; castle?: number | null; [k: string]: number | null | undefined };
  settlements: Settlement[];
  moved: number;
}

export interface NavmeshStats {
  faces: number;
  vertices: number;
  edges: number;
}

export interface Info {
  scene_dir: string;
  dirty: boolean;
  navmesh: NavmeshStats;
  terrain?: {
    world_size_x: number;
    world_size_y: number;
    min_height: number;
    max_height: number;
  };
}

export interface MeshResponse {
  vertices: number[];   // flat [x,y,z, x,y,z, ...]
  faces: number[][];    // each face: vertex ids (>=3)
  face_id: number[];    // g3 per face
  scene_level_mask: number[]; // signed g5 scene-level visibility bits per face
}

export interface TerrainResponse {
  rows?: number;
  cols?: number;
  world_size_x?: number;
  world_size_y?: number;
  heights?: number[];
}
