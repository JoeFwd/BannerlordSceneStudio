import { FADE_NEAR, FADE_FAR, LABEL_OPACITY } from './constants';

// Labels hold a constant ON-SCREEN size instead of a fixed world size. A fixed
// world-size label shrinks/grows with zoom, so the GPU minifies it by an
// ever-changing factor and its glyph brightness swims (the "flicker on approach"
// bug). Locking the on-screen size keeps the minification factor constant, so
// brightness is stable. Distant labels then fade out so a zoomed-out view is not
// a wall of same-size names.

// World units per screen pixel, per unit of camera distance.
export function worldPerPixelUnit(fovDeg: number, innerHeight: number): number {
  return (2 * Math.tan((fovDeg * Math.PI) / 360)) / innerHeight;
}

// World height that projects to a fixed on-screen pixel height at distance d.
export function labelWorldHeight(onPx: number, dist: number, wppUnit: number): number {
  return onPx * dist * wppUnit;
}

// Zoom fade: one global opacity from how far in you've zoomed, NOT per-label
// distance. `zoomDist` is the live camera->target distance; `fullViewDist` is the
// frozen full-view framing distance. Full white once you've zoomed to reading
// distance (<60% of full view), transparent as you pull back toward full view.
// This is deliberately label-independent: a distant label is exactly as bright as
// a near one at the same zoom, so panning across the map never leaves one name
// stuck white (the old per-label distance model scaled its "far" cutoff to the
// whole map, so far labels never dimmed).
export function labelFade(zoomDist: number, fullViewDist: number): number {
  if (!fullViewDist) return 1;
  const near = fullViewDist * FADE_NEAR;
  const far = fullViewDist * FADE_FAR;
  if (zoomDist <= near) return 1;
  if (zoomDist >= far) return 0;
  return (far - zoomDist) / (far - near);
}

export function labelOpacity(fade: number): number {
  return LABEL_OPACITY * fade;
}
