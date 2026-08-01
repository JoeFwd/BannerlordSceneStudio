// Every magic number the original inline scripts used, in one framework-free place.

export const MARK_LIFT = 2.0;
export const NAVMESH_LIFT = 0.15;      // lift navmesh tris above terrain
export const DEFAULT_WATER_LEVEL = 10.0;

// Marker colours (hex ints) — colour encodes the land/water/locked verdict.
export const C_LAND = 0x39d353;
export const C_PARTIAL = 0xe6a23c;
export const C_WATER = 0xe5484d;
export const C_REF = 0x6f7d9c;

// Per-type marker geometry dimensions (colour still encodes land/water/locked).
export const GEO = {
  townCone: { radius: 2.6, height: 5.4, radialSegments: 4 },
  castleCylinder: { radiusTop: 1.7, radiusBottom: 2.4, height: 4.6, radialSegments: 6 },
  villageSphere: { radius: 1.7, widthSegments: 12, heightSegments: 8 },
  unknownSphere: { radius: 1.4, widthSegments: 10, heightSegments: 8 },
} as const;

// Footprint disc/ring colours per type.
export const FP_COL: Record<string, number> = { town: 0x2d6cdf, castle: 0xd08a2d };
export const FP_FALLBACK = 0x888888;

// Label text size by type: towns much larger, castles medium, villages baseline.
export const LABEL_SCALE: Record<string, number> = { town: 1.9, castle: 1.35, village: 1.0 };

// Constant-on-screen label sizing + distance fade (fixes zoom-flicker + declutters).
export const SS = 2;                 // supersample the text canvas so glyphs stay crisp
export const ONSCREEN_PX = 15;       // village on-screen glyph height (px); town/castle scale up
export const LABEL_OPACITY = 1.0;    // full white when zoomed in; the distance fade dims it out
export const FADE_NEAR = 0.60;       // full white once you've zoomed to reading distance (<60% of full-view)
export const FADE_FAR = 0.85;        // fades out toward full-view height, gone beyond 85%
export const LABEL_FILL = '#ffffff'; // white text; brightness/whiteness rides on the zoom fade

// Scene / camera.
export const SCENE_BG = 0x151515;
export const CAM_FOV = 55;
export const CAM_NEAR = 0.5;
export const CAM_FAR = 20000;
export const ZOOM_SPEED = 2.0;
export const DEFAULT_PAN_REF_DIST = 800;
