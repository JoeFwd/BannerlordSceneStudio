import { create } from 'zustand';
import { studioApi } from '../api/studioApi';
import type { Settlement } from '../domain/types';
import { zoneWord } from '../domain/markerColor';
import { useStudioStore } from './studioStore';

const msg = (t: string) => useStudioStore.getState().setMsg(t);

interface EntitiesState {
  settlements: Settlement[];       // array identity changes only on (re)load — never on a staged move
  typeRadius: Record<string, number | null | undefined>;
  waterLevel: number;
  movedCount: number;
  moveInfo: string;                // transient "name: x, y (zone)" line under the counts
  selectedEnt: Settlement | null;
  labelsOn: boolean;
  visible: boolean;
  townR: string;
  castleR: string;
  customR: string;

  setField: (k: 'townR' | 'castleR' | 'customR', v: string) => void;
  loadEntities: () => Promise<void>;
  stageMove: (ent: Settlement, x: number, y: number) => Promise<Settlement | null>;
  resetMoves: () => Promise<void>;
  saveEntities: () => Promise<void>;
  saveTypeRadius: () => Promise<void>;
  saveCustomRadius: () => Promise<void>;
  selectEnt: (ent: Settlement) => void;
  toggleLabels: () => void;
  toggleVisible: () => void;
}

export const useEntitiesStore = create<EntitiesState>((set, get) => ({
  settlements: [],
  typeRadius: {},
  waterLevel: 10.0,
  movedCount: 0,
  moveInfo: '',
  selectedEnt: null,
  labelsOn: true,
  visible: true,
  townR: '',
  castleR: '',
  customR: '',

  setField: (k, v) => set({ [k]: v } as Partial<EntitiesState>),

  loadEntities: async () => {
    let data;
    try {
      data = await studioApi.getEntities();
    } catch {
      return;
    }
    const tr = data.type_radius || {};
    const patch: Partial<EntitiesState> = {
      settlements: data.settlements,
      typeRadius: tr,
      waterLevel: data.water_level ?? 10.0,
      movedCount: data.moved || 0,
      moveInfo: '',
    };
    if (tr.town != null) patch.townR = String(tr.town);
    if (tr.castle != null) patch.castleR = String(tr.castle);
    // reconcile the current selection against the freshly loaded records
    const sel = get().selectedEnt;
    if (sel) {
      const still = data.settlements.find((s) => s.id === sel.id) || null;
      patch.selectedEnt = still;
      patch.customR = still && still.radius != null ? String(still.radius) : '';
    }
    set(patch);
  },

  // Stages a move: mutates the settlement record in place (so the marker mesh and
  // probes see it without a rebuild) and bumps the counter that drives the info UI.
  stageMove: async (ent, x, y) => {
    let r: Settlement;
    try {
      r = await studioApi.moveEntity(ent.id, x, y);
    } catch {
      return null;
    }
    ent.x = r.x;
    ent.y = r.y;
    ent.height = r.height;
    ent.on_land = r.on_land;
    ent.land_fraction = r.land_fraction;
    const firstMove = !ent.moved;
    ent.moved = true;
    set((s) => ({
      movedCount: firstMove ? s.movedCount + 1 : s.movedCount,
      moveInfo: `${ent.name}: ${r.x.toFixed(1)}, ${r.y.toFixed(1)}  (${zoneWord(r)})`,
    }));
    return r;
  },

  resetMoves: async () => {
    await studioApi.resetMoves();
    await get().loadEntities();
    msg('moves reset');
  },

  saveEntities: async () => {
    if (!get().movedCount) return msg('no moves to save');
    try {
      const r = await studioApi.saveEntities();
      msg(`saved ${r.changed} settlement(s) · backups: ${(r.backups || []).join(', ')}`);
      await get().loadEntities();
    } catch (e) {
      msg('ERROR: ' + (e as Error).message);
    }
  },

  saveTypeRadius: async () => {
    const town = parseFloat(get().townR);
    const castle = parseFloat(get().castleR);
    const type_radius: Record<string, number | null> = {};
    if (town >= 0) type_radius.town = town;
    if (castle >= 0) type_radius.castle = castle;
    if (!Object.keys(type_radius).length) return msg('enter a town/castle radius');
    await studioApi.setTypeRadius(type_radius);
    msg('type radius saved');
    await get().loadEntities();
  },

  saveCustomRadius: async () => {
    const sel = get().selectedEnt;
    if (!sel) return msg('click a settlement to select it first');
    const v = get().customR.trim();
    const radius = v === '' ? null : parseFloat(v);
    if (v !== '' && !(radius! >= 0)) return msg('radius must be a number');
    const r = await studioApi.setCustomRadius(sel.id, radius);
    set({ selectedEnt: r, customR: r.radius != null ? String(r.radius) : '' });
    msg(`radius for ${r.name}: ${r.radius != null ? r.radius : '(type default)'}`);
    await get().loadEntities();
  },

  selectEnt: (ent) => {
    set({ selectedEnt: ent, customR: ent.radius != null ? String(ent.radius) : '' });
    msg(`selected ${ent.name}`);
  },

  toggleLabels: () => set((s) => ({ labelsOn: !s.labelsOn })),
  toggleVisible: () => set((s) => ({ visible: !s.visible })),
}));
