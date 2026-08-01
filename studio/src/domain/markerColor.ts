import { C_LAND, C_PARTIAL, C_WATER, C_REF } from './constants';
import type { Settlement } from './types';

// Zone-based verdict: green = fully on land, amber = zone partly on land (valid,
// e.g. a coastal/riverside settlement), red = zone entirely in water (invalid),
// grey = locked reference settlement.
export function markerColor(s: Pick<Settlement, 'movable' | 'land_fraction' | 'on_land'>): number {
  if (!s.movable) return C_REF;
  const f = s.land_fraction;
  if (f == null) return s.on_land ? C_LAND : C_WATER;
  if (f >= 0.999) return C_LAND;
  return f > 0 ? C_PARTIAL : C_WATER;
}

// Human word for a settlement's zone verdict.
export function zoneWord(s: Pick<Settlement, 'land_fraction' | 'on_land'>): string {
  const f = s.land_fraction;
  if (f == null) return s.on_land ? 'land' : 'WATER';
  if (f >= 0.999) return 'land';
  return f > 0 ? `part land ${Math.round(f * 100)}%` : 'WATER';
}

// '#rrggbb' form for the DOM/probe surface.
export const hexString = (color: number): string => '#' + color.toString(16).padStart(6, '0');
