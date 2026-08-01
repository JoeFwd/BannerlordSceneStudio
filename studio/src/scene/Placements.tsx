import { useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { OrbitControls } from 'three-stdlib';
import { useEntitiesStore } from '../state/entitiesStore';
import { markerColor, zoneWord } from '../domain/markerColor';
import { MARK_LIFT } from '../domain/constants';
import { worldPerPixelUnit, labelWorldHeight, labelFade, labelOpacity } from '../domain/labelSizing';
import { buildMarkers, type BuiltMarkers } from './builders';
import { sceneRefs } from './sceneRefs';
import { interaction } from './interaction';
import { tip } from '../ui/tip';

const ray = new THREE.Raycaster();
const mouse = new THREE.Vector2();

export function Placements() {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  const controls = useThree((s) => s.controls) as unknown as OrbitControls | null;

  const settlements = useEntitiesStore((s) => s.settlements);
  const waterLevel = useEntitiesStore((s) => s.waterLevel);
  const visible = useEntitiesStore((s) => s.visible);
  const stageMove = useEntitiesStore((s) => s.stageMove);
  const selectEnt = useEntitiesStore((s) => s.selectEnt);

  const built = useMemo<BuiltMarkers | null>(
    () => buildMarkers(settlements, waterLevel, useEntitiesStore.getState().labelsOn, gl.capabilities.getMaxAnisotropy()),
    // Rebuild only when the settlement set changes identity (load/reset/save/radius);
    // a staged drag mutates records in place and must NOT trigger a rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [settlements, waterLevel],
  );

  useEffect(() => {
    sceneRefs.markers = built ? built.markers : [];
    return () => { sceneRefs.markers = []; };
  }, [built]);

  // Group visibility toggle (also drops the hover tooltip when hidden).
  useEffect(() => {
    if (!built) return;
    built.group.visible = visible;
    if (!visible) { interaction.overMarker = false; tip.hide(); }
  }, [built, visible]);

  // Constant-on-screen label sizing + distance fade, every frame.
  useFrame(() => {
    const labelsOn = useEntitiesStore.getState().labelsOn;
    const ref = sceneRefs.panRefDist || 0;
    const wpp = worldPerPixelUnit(camera.fov, innerHeight);
    for (const r of sceneRefs.markers) {
      const spr = r.label;
      if (!spr) continue;
      const p = spr.parent;
      if (!p) continue;
      const d = camera.position.distanceTo(p.position);
      const h = labelWorldHeight(spr.userData.onPx as number, d, wpp);
      spr.scale.set(h * (spr.userData.aspect as number), h, 1);
      const fade = labelFade(d, ref);
      (spr.material as THREE.SpriteMaterial).opacity = labelOpacity(fade);
      spr.visible = labelsOn && fade > 0.02;
    }
  });

  // Pixel-accurate marker drag / pick / select — window-level capture listeners,
  // matching the original so Playwright's synthetic mouse events drive it.
  useEffect(() => {
    const dom = gl.domElement;
    let dragMesh: THREE.Mesh | null = null;
    let dragMoved = false;
    let lastMove = 0;

    const pickMarker = (e: PointerEvent): THREE.Mesh | null => {
      if (!built || !built.group.visible || !sceneRefs.markers.length) return null;
      mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
      ray.setFromCamera(mouse, camera);
      const hit = ray.intersectObjects(sceneRefs.markers.map((r) => r.mesh), false)[0];
      return hit ? (hit.object as THREE.Mesh) : null;
    };

    const doMove = (mesh: THREE.Mesh, x: number, y: number) => {
      const ent = mesh.userData.ent;
      stageMove(ent, x, y).then(() => {
        (mesh.material as THREE.MeshBasicMaterial).color.setHex(markerColor(ent));
      });
    };

    const onDown = (e: PointerEvent) => {
      if (e.button !== 0 || e.target !== dom) return;
      const m = pickMarker(e);
      if (!m || !m.userData.ent.movable) return;
      interaction.markerDrag = true; dragMesh = m; dragMoved = false;
      if (controls) controls.enabled = false;
      document.body.style.cursor = 'grabbing';
      e.stopPropagation();
    };

    const onMove = (e: PointerEvent) => {
      if (interaction.markerDrag) {
        const terrain = sceneRefs.terrainMesh;
        if (!terrain || !dragMesh) return;
        mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
        ray.setFromCamera(mouse, camera);
        const hit = ray.intersectObject(terrain)[0];
        if (hit) {
          const wx = hit.point.x, wy = -hit.point.z;
          dragMoved = true;
          dragMesh.position.set(hit.point.x, Math.max(hit.point.y, useEntitiesStore.getState().waterLevel) + MARK_LIFT, hit.point.z);
          tip.show(`${dragMesh.userData.ent.name}  ${wx.toFixed(1)}, ${wy.toFixed(1)}`, e.clientX, e.clientY);
          const now = performance.now();
          if (now - lastMove > 70) { lastMove = now; doMove(dragMesh, wx, wy); }
        }
        e.stopPropagation();
        return;
      }
      if (e.target !== dom) return;
      const m = pickMarker(e);
      if (m) {
        interaction.overMarker = true;
        const ent = m.userData.ent;
        const flag = ent.movable ? zoneWord(ent) : 'locked';
        tip.show(`${ent.name} · ${ent.type || '?'} · ${flag}${ent.moved ? ' · moved' : ''}`, e.clientX, e.clientY);
      } else if (interaction.overMarker) {
        interaction.overMarker = false; tip.hide();
      }
    };

    const onUp = (e: PointerEvent) => {
      if (!interaction.markerDrag) return;
      if (dragMoved && dragMesh) {
        const p = dragMesh.position;
        doMove(dragMesh, p.x, -p.z); // final authoritative position
      } else if (dragMesh) {
        selectEnt(dragMesh.userData.ent); // a click without a drag = select
      }
      interaction.markerDrag = false; dragMesh = null;
      if (controls) controls.enabled = true;
      document.body.style.cursor = '';
      e.stopPropagation();
    };

    window.addEventListener('pointerdown', onDown, true);
    window.addEventListener('pointermove', onMove, true);
    window.addEventListener('pointerup', onUp, true);
    return () => {
      window.removeEventListener('pointerdown', onDown, true);
      window.removeEventListener('pointermove', onMove, true);
      window.removeEventListener('pointerup', onUp, true);
    };
  }, [built, gl, camera, controls, stageMove, selectEnt]);

  if (!built) return null;
  return <primitive object={built.group} />;
}
