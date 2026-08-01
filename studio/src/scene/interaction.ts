// Per-frame imperative pointer flags shared between the marker layer (which sets
// them) and the navmesh hover/select layer (which reads them to yield the tooltip
// during a marker drag/hover). These are transient interaction state, never React
// state — mirrors the original store.markerDrag / store.overMarker fields.
export const interaction = {
  markerDrag: false,
  overMarker: false,
};
