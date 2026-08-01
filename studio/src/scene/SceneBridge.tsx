import { useEffect } from 'react';
import { useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { OrbitControls } from 'three-stdlib';
import { sceneRefs } from './sceneRefs';
import { installProbes } from '../probes/installProbes';

// Bridges the live R3F objects into sceneRefs and installs the window.__* probes.
// Lives inside <Canvas> so it can read useThree; renders nothing.
export function SceneBridge() {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const controls = useThree((s) => s.controls) as unknown as OrbitControls | null;

  useEffect(() => { sceneRefs.camera = camera; }, [camera]);
  useEffect(() => { sceneRefs.controls = controls; }, [controls]);
  useEffect(() => { installProbes(); }, []);

  return null;
}
