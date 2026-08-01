import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { CAM_FOV, CAM_NEAR, CAM_FAR, ZOOM_SPEED, SCENE_BG } from '../domain/constants';
import { SceneBridge } from './SceneBridge';
import { Terrain } from './Terrain';
import { Navmesh } from './Navmesh';
import { Placements } from './Placements';
import { CameraController } from './CameraController';

// The full-window 3D view. All framework config lives here; feature layers are
// declarative children.
export function Studio() {
  return (
    <Canvas
      flat  // NoToneMapping — R3F defaults to ACESFilmic, which desaturates the vivid
            // terrain/water colours; the vanilla renderer used no tone mapping.
      gl={{ antialias: true }}
      camera={{ fov: CAM_FOV, near: CAM_NEAR, far: CAM_FAR }}
      onCreated={({ scene }) => { scene.background = new THREE.Color(SCENE_BG); }}
      style={{ position: 'absolute', inset: 0, width: '100vw', height: '100vh' }}
    >
      <ambientLight intensity={0.7} />
      <directionalLight intensity={1.2} position={[1, 2, 1]} />
      <OrbitControls makeDefault zoomSpeed={ZOOM_SPEED} />
      <SceneBridge />
      <Terrain />
      <Navmesh />
      <Placements />
      <CameraController />
    </Canvas>
  );
}
