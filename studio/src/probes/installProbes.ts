// Re-installs the window.__* debug probes the E2E suite reads. They project the
// LIVE three objects held in sceneRefs — identical output to the original inline
// script's helpers. Called once, after the Canvas is created.
import { sceneRefs } from '../scene/sceneRefs';
import { hexString } from '../domain/markerColor';
import { useEntitiesStore } from '../state/entitiesStore';

export function installProbes(): void {
  const w = window as unknown as Record<string, unknown>;

  w.__markerScreens = () => {
    const cam = sceneRefs.camera;
    if (!cam) return [];
    return sceneRefs.markers.map((r) => {
      const v = r.mesh.position.clone().project(cam);
      const ent = r.ent;
      return {
        id: ent.id,
        movable: ent.movable,
        on_land: ent.on_land,
        land_fraction: ent.land_fraction,
        color: '#' + (r.mesh.material as unknown as { color: { getHexString(): string } }).color.getHexString(),
        visible: v.z < 1,
        x: (v.x * 0.5 + 0.5) * innerWidth,
        y: (-v.y * 0.5 + 0.5) * innerHeight,
      };
    });
  };

  w.__labelSizes = () => {
    const acc: Record<string, number[]> = {};
    for (const r of sceneRefs.markers) {
      if (!r.ent.movable || !r.label) continue;
      (acc[r.ent.type] = acc[r.ent.type] || []).push(r.label.scale.y);
    }
    const out: Record<string, number> = {};
    for (const t in acc) out[t] = acc[t].reduce((a, b) => a + b, 0) / acc[t].length;
    return out; // avg label world-height per type
  };

  w.__entStats = () => {
    const geo = { cone: 0, cylinder: 0, sphere: 0 };
    let rings = 0;
    for (const r of sceneRefs.markers) {
      const g = r.mesh.geometry.type;
      if (g === 'ConeGeometry') geo.cone++;
      else if (g === 'CylinderGeometry') geo.cylinder++;
      else geo.sphere++;
      if (r.footprint) rings++;
    }
    const sel = useEntitiesStore.getState().selectedEnt;
    return {
      markers: sceneRefs.markers.length,
      labels: sceneRefs.markers.filter((r) => r.label).length,
      footprintRings: rings,
      shapes: geo,
      selected: sel && sel.id,
    };
  };

  w.__cam = () => {
    const cam = sceneRefs.camera;
    const c = sceneRefs.controls;
    if (!cam || !c) return { tx: 0, tz: 0, dist: 0, panRef: sceneRefs.panRefDist };
    return {
      tx: c.target.x,
      tz: c.target.z,
      dist: cam.position.distanceTo(c.target),
      panRef: sceneRefs.panRefDist,
    };
  };
}

// keep hexString referenced so tree-shaking parity with the original (colour fmt)
void hexString;
