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

// Distance fade: full opacity near, transparent far, linear between.
export function labelFade(dist: number, panRefDist: number): number {
  if (!panRefDist) return 1;
  const near = panRefDist * FADE_NEAR;
  const far = panRefDist * FADE_FAR;
  if (dist <= near) return 1;
  if (dist >= far) return 0;
  return (far - dist) / (far - near);
}

export function labelOpacity(fade: number): number {
  return LABEL_OPACITY * fade;
}
