// The one place HTTP lives. A single concrete module — deliberately NOT behind an
// interface: there is exactly one implementation and the E2E suite exercises the
// real backend (no mock). If a second backend or a test double ever appears,
// extract an interface then. This is the thin seam between UI and the server.
import type { EntitiesResponse, Info, MeshResponse, Settlement, TerrainResponse } from '../domain/types';

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(
    path,
    body === undefined
      ? undefined
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export interface GenerateReq {
  cell_size: number;
  max_slope_deg: number;
  replace: boolean;
  min_x?: number;
  min_y?: number;
  max_x?: number;
  max_y?: number;
}

export const studioApi = {
  getInfo: () => request<Info>('/api/info'),
  getMesh: () => request<MeshResponse>('/api/mesh'),
  getTerrain: (maxDim = 256) => request<TerrainResponse>(`/api/terrain?max_dim=${maxDim}`),
  getEntities: () => request<EntitiesResponse>('/api/entities'),

  loadScene: (scene_dir: string) => request<Info>('/api/load', { scene_dir }),
  browse: () => request<{ path: string | null }>('/api/browse'),

  generate: (req: GenerateReq) => request<Info>('/api/generate', req),
  setAttrs: (indices: number[], face_id: number, group: number) =>
    request<{ changed: number }>('/api/set_attrs', { indices, face_id, group }),
  deleteFaces: (indices: number[]) => request<Info>('/api/delete_faces', { indices }),
  saveMesh: () => request<{ path: string }>('/api/save', {}),

  moveEntity: (id: string, x: number, y: number) =>
    request<Settlement>('/api/move_entity', { id, x, y }),
  resetMoves: () => request<{ cleared: number }>('/api/reset_moves', {}),
  saveEntities: () => request<{ changed: number; backups?: string[] }>('/api/save_entities', {}),
  setTypeRadius: (type_radius: Record<string, number | null>) =>
    request<{ type_radius: Record<string, number | null> }>('/api/set_type_radius', { type_radius }),
  setCustomRadius: (id: string, radius: number | null) =>
    request<Settlement>('/api/set_custom_radius', { id, radius }),
};

export type StudioApi = typeof studioApi;
