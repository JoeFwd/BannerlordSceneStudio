import { create } from 'zustand';
import { CAMPAIGN_REQUIRED_LEVELS } from '../domain/sceneLevels';
import { studioApi, type GenerateReq } from '../api/studioApi';
import type { Info, MeshResponse, TerrainResponse } from '../domain/types';
import type { ColorMode } from '../domain/terrainColors';
import { useEntitiesStore } from './entitiesStore';

function isCampaignScene(sceneDir: string): boolean {
  return sceneDir.replace(/[\\/]+$/, '').split(/[\\/]/).pop()?.toLowerCase() === 'main_map';
}

function statsFrom(info: Info): string {
  const s = info.navmesh;
  let txt = `scene: ${info.scene_dir}\nfaces: ${s.faces}  verts: ${s.vertices}  edges: ${s.edges}`;
  if (info.terrain) txt += `\nterrain: ${info.terrain.world_size_x}x${info.terrain.world_size_y} m`;
  txt += info.dirty ? '\n[UNSAVED CHANGES]' : '';
  return txt;
}

interface StudioState {
  info: Info | null;
  sceneDir: string;
  statsText: string;
  isCampaign: boolean;
  mesh: MeshResponse | null;
  terrain: TerrainResponse | null;
  colorMode: ColorMode;
  selection: Set<number>;
  terrainVisible: boolean;
  rawNavmesh: boolean;
  requiredSceneLevels: number;
  msg: string;
  // navmesh generation / attribute form inputs
  cellSize: string;
  maxSlope: string;
  region: string;
  faceId: string;
  sceneLevelMask: string;

  setMsg: (t: string) => void;
  setField: (k: 'sceneDir' | 'cellSize' | 'maxSlope' | 'region' | 'faceId' | 'sceneLevelMask', v: string) => void;
  setColorMode: (v: ColorMode) => void;
  toggleTerrain: () => void;
  toggleRawNavmesh: () => void;
  toggleCampaignLevels: () => void;

  init: () => Promise<void>;
  loadScene: () => Promise<void>;
  browse: () => Promise<void>;
  generate: (replace: boolean) => Promise<void>;
  selectFaceAt: (fi: number, additive: boolean) => void;
  clearSelection: (additive: boolean) => void;
  applyAttrs: () => Promise<void>;
  deleteSelection: () => Promise<void>;
  saveMesh: () => Promise<void>;

  _applyInfo: (info: Info) => void;
  _reloadMesh: () => Promise<void>;
}

export const useStudioStore = create<StudioState>((set, get) => ({
  info: null,
  sceneDir: '',
  statsText: 'no scene loaded',
  isCampaign: false,
  mesh: null,
  terrain: null,
  colorMode: 'terrain',
  selection: new Set(),
  terrainVisible: true,
  rawNavmesh: false,
  requiredSceneLevels: 0,
  msg: '',
  cellSize: '4',
  maxSlope: '40',
  region: '',
  faceId: '0',
  sceneLevelMask: '',

  setMsg: (t) => set({ msg: t }),
  setField: (k, v) => set({ [k]: v } as Partial<StudioState>),
  setColorMode: (v) => set({ colorMode: v }),
  toggleTerrain: () => set((s) => ({ terrainVisible: !s.terrainVisible })),
  toggleRawNavmesh: () => set((s) => ({ rawNavmesh: !s.rawNavmesh })),

  toggleCampaignLevels: () => set((s) => ({
    requiredSceneLevels: s.requiredSceneLevels ? 0 : CAMPAIGN_REQUIRED_LEVELS,
    selection: new Set(),
  })),

  _applyInfo: (info) => set((s) => {
    const isCampaign = isCampaignScene(info.scene_dir);
    return { info, sceneDir: info.scene_dir, statsText: statsFrom(info), isCampaign,
      requiredSceneLevels: s.info?.scene_dir === info.scene_dir ? s.requiredSceneLevels : (isCampaign ? CAMPAIGN_REQUIRED_LEVELS : 0) };
  }),

  _reloadMesh: async () => {
    const mesh = await studioApi.getMesh();
    set({ mesh });
  },

  init: async () => {
    try {
      const info = await studioApi.getInfo();
      get()._applyInfo(info);
      const [terrain] = await Promise.all([studioApi.getTerrain()]);
      set({ terrain });
      await get()._reloadMesh();
      await useEntitiesStore.getState().loadEntities();
    } catch {
      /* no scene preloaded */
    }
  },

  loadScene: async () => {
    set({ msg: 'loading…' });
    try {
      const info = await studioApi.loadScene(get().sceneDir);
      get()._applyInfo(info);
      set({ selection: new Set() });
      const terrain = await studioApi.getTerrain();
      set({ terrain });
      await get()._reloadMesh();
      await useEntitiesStore.getState().loadEntities();
      set({ msg: 'loaded' });
    } catch (e) {
      set({ msg: 'ERROR: ' + (e as Error).message });
    }
  },

  browse: async () => {
    set({ msg: 'pick a folder in the dialog (check the taskbar)…' });
    try {
      const r = await studioApi.browse();
      if (!r.path) return set({ msg: 'folder selection cancelled' });
      set({ sceneDir: r.path });
      await get().loadScene();
    } catch (e) {
      set({ msg: 'ERROR: ' + (e as Error).message });
    }
  },

  generate: async (replace) => {
    set({ msg: 'generating…' });
    const req: GenerateReq = {
      cell_size: parseFloat(get().cellSize),
      max_slope_deg: parseFloat(get().maxSlope),
      replace,
    };
    const r = get().region.trim();
    if (r) {
      const [a, b, c, d] = r.split(',').map(parseFloat);
      Object.assign(req, { min_x: a, min_y: b, max_x: c, max_y: d });
    }
    try {
      const info = await studioApi.generate(req);
      get()._applyInfo(info);
      set({ selection: new Set() });
      await get()._reloadMesh();
      set({ msg: 'generated' });
    } catch (e) {
      set({ msg: 'ERROR: ' + (e as Error).message });
    }
  },

  // Click on a face: non-shift replaces the selection with this face; shift toggles
  // it in/out of a multi-selection. (additive === shiftKey.)
  selectFaceAt: (fi, additive) =>
    set((s) => {
      const sel = additive ? new Set(s.selection) : new Set<number>();
      if (sel.has(fi)) sel.delete(fi);
      else sel.add(fi);
      const selected = [...sel];
      const masks = new Set(selected.map((i) => s.mesh?.scene_level_mask[i]));
      return { selection: sel,
        faceId: selected.length === 1 ? String(s.mesh?.face_id[selected[0]]) : s.faceId,
        sceneLevelMask: masks.size === 1 ? String(s.mesh?.scene_level_mask[selected[0]]) : '' };
    }),

  // Click on empty space: non-shift clears; shift keeps the current selection.
  clearSelection: (additive) => set(additive ? {} : { selection: new Set<number>() }),

  applyAttrs: async () => {
    const { selection, faceId, sceneLevelMask } = get();
    if (!selection.size) return set({ msg: 'nothing selected' });
    try {
      const mask = sceneLevelMask.trim() === '' ? undefined : Number(sceneLevelMask);
      if (mask !== undefined && (!Number.isInteger(mask) || mask < -2147483648 || mask > 2147483647)) {
        throw new Error('Scene-level mask must be a signed 32-bit integer');
      }
      await studioApi.setAttrs([...selection], parseInt(faceId), mask);
      await get()._reloadMesh();
      set({ msg: 'attributes applied' });
    } catch (e) {
      set({ msg: 'ERROR: ' + (e as Error).message });
    }
  },

  deleteSelection: async () => {
    const { selection } = get();
    if (!selection.size) return set({ msg: 'nothing selected' });
    try {
      const info = await studioApi.deleteFaces([...selection]);
      get()._applyInfo(info);
      set({ selection: new Set() });
      await get()._reloadMesh();
      set({ msg: 'deleted' });
    } catch (e) {
      set({ msg: 'ERROR: ' + (e as Error).message });
    }
  },

  saveMesh: async () => {
    try {
      const r = await studioApi.saveMesh();
      set({ msg: 'saved: ' + r.path });
      const info = await studioApi.getInfo();
      get()._applyInfo(info);
    } catch (e) {
      set({ msg: 'ERROR: ' + (e as Error).message });
    }
  },
}));
