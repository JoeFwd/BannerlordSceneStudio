import { useEffect, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { OrbitControls } from 'three-stdlib';
import { panToken, effectiveDist, panSpeed, type PanToken } from '../domain/panEasing';
import { sceneRefs } from './sceneRefs';

const _fwd = new THREE.Vector3();
const _right = new THREE.Vector3();
const _delta = new THREE.Vector3();
const _up = new THREE.Vector3(0, 1, 0);

const typingInField = () => {
  const t = document.activeElement && document.activeElement.tagName;
  return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT';
};

// Keyboard pan (WASD / ZQSD / arrows) by physical key position. Eases with zoom.
export function CameraController() {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const controls = useThree((s) => s.controls) as unknown as OrbitControls | null;
  const keys = useRef<Set<PanToken>>(new Set());

  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      if (typingInField() || e.ctrlKey || e.metaKey || e.altKey) return;
      const tok = panToken(e.code);
      if (tok) { keys.current.add(tok); e.preventDefault(); }
    };
    const onUp = (e: KeyboardEvent) => { const tok = panToken(e.code); if (tok) keys.current.delete(tok); };
    const onBlur = () => keys.current.clear();
    addEventListener('keydown', onDown);
    addEventListener('keyup', onUp);
    addEventListener('blur', onBlur);
    return () => {
      removeEventListener('keydown', onDown);
      removeEventListener('keyup', onUp);
      removeEventListener('blur', onBlur);
    };
  }, []);

  useFrame((_, dt) => {
    const k = keys.current;
    if (!k.size || !controls) return;
    _fwd.subVectors(controls.target, camera.position); _fwd.y = 0;
    if (_fwd.lengthSq() < 1e-9) return;
    _fwd.normalize();
    _right.crossVectors(_fwd, _up).normalize();
    _delta.set(0, 0, 0);
    if (k.has('fwd')) _delta.add(_fwd);
    if (k.has('back')) _delta.sub(_fwd);
    if (k.has('right')) _delta.add(_right);
    if (k.has('left')) _delta.sub(_right);
    if (_delta.lengthSq() === 0) return;
    const liveDist = camera.position.distanceTo(controls.target);
    const speed = panSpeed(effectiveDist(liveDist, sceneRefs.panRefDist));
    _delta.normalize().multiplyScalar(speed * dt);
    camera.position.add(_delta);
    controls.target.add(_delta);
    controls.update();
  });

  return null;
}
