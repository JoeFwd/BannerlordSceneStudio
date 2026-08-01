// Campaign-map face colouring + legend. Pure: returns normalised [r,g,b] triples
// and '#rrggbb' strings, with no three.js dependency.

export type RGB = [number, number, number];

// TaleWorlds.Core.TerrainType — campaign map navmesh face group ids (g3).
export const TERRAIN: Record<number, [string, string]> = {
  0: ['(unset)', '#777777'], 1: ['Plain', '#7bb661'],
  2: ['Desert', '#d9c27a'], 3: ['Snow', '#eef2f5'],
  4: ['Forest', '#2e6b2e'], 5: ['Steppe', '#b5b35c'],
  6: ['Fording', '#7ec8d4'], 7: ['Mountain', '#8a8a92'],
  8: ['Lake', '#3f7fbf'], 10: ['Water', '#2c5fa8'],
  11: ['River', '#4f8fd0'], 13: ['Canyon', '#a0653b'],
  14: ['RuralArea', '#e0954f'], 15: ['Swamp', '#5d7a4c'],
  16: ['Dune', '#e3cd8f'], 17: ['Bridge', '#9c7b5a'],
  18: ['CoastalSea', '#2a4f8f'], 19: ['OpenSea', '#1c3a70'],
  20: ['Beach', '#e8d9a0'], 21: ['Cliff', '#5a5a60'],
  22: ['NonNavigableRiver', '#6fa3c8'], 23: ['LandRestriction', '#b04040'],
  24: ['SeaRestriction', '#703070'], 25: ['UnderBridge', '#77808a'],
};

export type ColorMode = 'terrain' | 'island';

export interface FaceColorContext {
  colorMode: ColorMode;
  isCampaign: boolean;
  faceId: number[];   // g3 per face (empty when no mesh)
  group: number[];    // g5 per face
  selection: Set<number>;
}

// --- colour maths (matches three.js Color.setHSL / hex parsing exactly) -------
export function hexToRgb(hex: string): RGB {
  const n = parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export function rgbToHex([r, g, b]: RGB): string {
  const to = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
  return to(r) + to(g) + to(b);
}

// three.js Color.setHSL(h,s,l).
export function hslToRgb(h: number, s: number, l: number): RGB {
  h = ((h % 1) + 1) % 1;
  if (s === 0) return [l, l, l];
  const p = l <= 0.5 ? l * (1 + s) : l + s - l * s;
  const q = 2 * l - p;
  const hue2rgb = (t: number): number => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return q + (p - q) * 6 * t;
    if (t < 1 / 2) return p;
    if (t < 2 / 3) return q + (p - q) * 6 * (2 / 3 - t);
    return q;
  };
  return [hue2rgb(h + 1 / 3), hue2rgb(h), hue2rgb(h - 1 / 3)];
}

export function keyColor(k: number, ctx: Pick<FaceColorContext, 'colorMode' | 'isCampaign'>): RGB {
  if (ctx.colorMode === 'terrain' && ctx.isCampaign && TERRAIN[k]) return hexToRgb(TERRAIN[k][1]);
  const hue = ((((k % 12) + 12) % 12)) / 12;
  return hslToRgb(0.55 + 0.35 * hue, 0.75, 0.55);
}

export function faceColor(i: number, ctx: FaceColorContext): RGB {
  if (ctx.selection.has(i)) return [1.0, 0.15, 0.75];
  if (!ctx.faceId.length) return [0.3, 0.5, 0.8];
  return keyColor(ctx.colorMode === 'island' ? ctx.group[i] : ctx.faceId[i], ctx);
}

export function faceLabel(
  i: number,
  ctx: Pick<FaceColorContext, 'isCampaign' | 'faceId' | 'group'>,
): string {
  const id = ctx.faceId[i];
  const name = ctx.isCampaign && TERRAIN[id] ? ` (${TERRAIN[id][0]})` : '';
  return `face #${i} · id ${id}${name} · island ${ctx.group[i]}`;
}

export interface LegendRow {
  key: number;
  label: string;
  swatch: string;   // '#rrggbb'
  count: number;
}

export function legendRows(ctx: FaceColorContext): { rows: LegendRow[]; overflow: boolean } {
  if (!ctx.faceId.length) return { rows: [], overflow: false };
  const vals = ctx.colorMode === 'island' ? ctx.group : ctx.faceId;
  const counts = new Map<number, number>();
  for (const v of vals) counts.set(v, (counts.get(v) || 0) + 1);
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const rows = sorted.slice(0, 24).map(([k, n]) => {
    const label = ctx.colorMode === 'terrain' && ctx.isCampaign && TERRAIN[k]
      ? `${TERRAIN[k][0]} (${k})` : `${k}`;
    return { key: k, label, swatch: '#' + rgbToHex(keyColor(k, ctx)), count: n };
  });
  return { rows, overflow: counts.size > 24 };
}
