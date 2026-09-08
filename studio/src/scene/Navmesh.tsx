import { useEffect, useMemo, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { OrbitControls } from 'three-stdlib';
import { useStudioStore } from '../state/studioStore';
import { faceLabel } from '../domain/terrainColors';
import { buildNavmesh, repaintNavmesh, type BuiltNavmesh } from './builders';
import { sceneRefs } from './sceneRefs';
import { interaction } from './interaction';
import { tip } from '../ui/tip';
import type { MeshResponse } from '../domain/types';
import { NAVMESH_LIFT } from '../domain/constants';

const ray = new THREE.Raycaster();
const mouse = new THREE.Vector2();

export function Navmesh() {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  const controls = useThree((s) => s.controls) as unknown as OrbitControls | null;

  const mesh = useStudioStore((s) => s.mesh);
  const colorMode = useStudioStore((s) => s.colorMode);
  const selection = useStudioStore((s) => s.selection);
  const isCampaign = useStudioStore((s) => s.isCampaign);
  const requiredSceneLevels = useStudioStore((s) => s.requiredSceneLevels);
  const rawNavmesh = useStudioStore((s) => s.rawNavmesh);
  const selectFaceAt = useStudioStore((s) => s.selectFaceAt);
  const clearSelection = useStudioStore((s) => s.clearSelection);

  const built = useMemo<BuiltNavmesh | null>(
    () => (mesh ? buildNavmesh(mesh, selection, colorMode, isCampaign, requiredSceneLevels) : null),
    // Rebuild only on new mesh data; selection/colorMode drive repaint, not rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mesh, requiredSceneLevels],
  );
  const builtRef = useRef<BuiltNavmesh | null>(null);
  builtRef.current = built;

  // Keep the camera and serialized data unchanged when comparing raw geometry
  // against Studio's lifted, double-sided convenience view.
  useEffect(() => {
    if (!built) return;
    built.group.position.y = rawNavmesh ? -NAVMESH_LIFT : 0;
    const material = built.navMesh.material as THREE.MeshBasicMaterial;
    material.side = rawNavmesh ? THREE.FrontSide : THREE.DoubleSide;
    material.needsUpdate = true;
  }, [built, rawNavmesh]);

  const framedMesh = useRef<MeshResponse | null>(null);
  // Register the pickable surface + frame the camera once per new mesh.
  useEffect(() => {
    sceneRefs.navMesh = built ? built.navMesh : null;
    if (built && built.boundingSphere && controls && framedMesh.current !== mesh) {
      framedMesh.current = mesh;
      const bs = built.boundingSphere;
      controls.target.copy(bs.center);
      camera.position.set(bs.center.x + bs.radius, bs.center.y + bs.radius * 0.9, bs.center.z + bs.radius);
      controls.update();
      sceneRefs.panRefDist = camera.position.distanceTo(controls.target); // freeze full-view pan speed
    }
    return () => {
      if (sceneRefs.navMesh === (built && built.navMesh)) sceneRefs.navMesh = null;
    };
  }, [built, camera, controls, mesh]);

  // Repaint vertex colours when selection or colour mode changes.
  useEffect(() => {
    if (built && mesh) repaintNavmesh(built, mesh, selection, colorMode, isCampaign);
  }, [built, mesh, selection, colorMode, isCampaign]);

  // Hover tooltip (throttled) + click-to-select, on the canvas element.
  useEffect(() => {
    const dom = gl.domElement;
    let lastHover = 0;
    let downAt: [number, number] | null = null;

    const onMove = (e: PointerEvent) => {
      if (interaction.markerDrag || interaction.overMarker) return;
      const b = builtRef.current;
      if (!b || !mesh || !mesh.face_id.length) { tip.hide(); return; }
      const now = performance.now();
      if (now - lastHover < 30) return;
      lastHover = now;
      mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
      ray.setFromCamera(mouse, camera);
      const hit = ray.intersectObject(b.navMesh)[0];
      if (!hit || hit.faceIndex == null) { tip.hide(); return; }
      const fi = b.triToFace[hit.faceIndex];
      tip.show(faceLabel(fi, { isCampaign, faceId: mesh.face_id, sceneLevelMask: mesh.scene_level_mask }), e.clientX, e.clientY);
    };
    const onDown = (e: PointerEvent) => { downAt = [e.clientX, e.clientY]; };
    const onUp = (e: PointerEvent) => {
      if (interaction.markerDrag) return;
      const b = builtRef.current;
      if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4 || !b) return;
      mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
      ray.setFromCamera(mouse, camera);
      const hit = ray.intersectObject(b.navMesh)[0];
      if (!hit || hit.faceIndex == null) { clearSelection(e.shiftKey); return; }
      selectFaceAt(b.triToFace[hit.faceIndex], e.shiftKey);
    };

    dom.addEventListener('pointermove', onMove);
    dom.addEventListener('pointerdown', onDown);
    dom.addEventListener('pointerup', onUp);
    return () => {
      dom.removeEventListener('pointermove', onMove);
      dom.removeEventListener('pointerdown', onDown);
      dom.removeEventListener('pointerup', onUp);
    };
  }, [gl, camera, mesh, isCampaign, selectFaceAt, clearSelection]);

  if (!built) return null;
  return <primitive object={built.group} />;
}
