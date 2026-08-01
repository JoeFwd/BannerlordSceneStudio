import * as THREE from 'three';
import { camera, controls } from './scene.js';
import { store } from './store.js';

// ---- keyboard pan (WASD on QWERTY == ZQSD on AZERTY, via physical e.code) ----
// e.code is layout-independent physical position: KeyW/KeyA/KeyS/KeyD is the
// same physical diamond that is labelled W/A/S/D on QWERTY and Z/Q/S/D on AZERTY.
const panKeys = new Set();
function panToken(code) {
  switch (code) {
    case 'KeyW': case 'ArrowUp':    return 'fwd';
    case 'KeyS': case 'ArrowDown':  return 'back';
    case 'KeyA': case 'ArrowLeft':  return 'left';
    case 'KeyD': case 'ArrowRight': return 'right';
  }
  return null;
}
const typingInField = () => {
  const t = document.activeElement && document.activeElement.tagName;
  return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT';
};
addEventListener('keydown', e => {
  if (typingInField() || e.ctrlKey || e.metaKey || e.altKey) return;
  const tok = panToken(e.code);
  if (tok) { panKeys.add(tok); e.preventDefault(); }
});
addEventListener('keyup', e => { const tok = panToken(e.code); if (tok) panKeys.delete(tok); });
addEventListener('blur', () => panKeys.clear());

const _fwd = new THREE.Vector3(), _right = new THREE.Vector3(), _delta = new THREE.Vector3();
const _up = new THREE.Vector3(0, 1, 0);
export const clock = new THREE.Clock();
export function applyPan(dt) {
  if (!panKeys.size) return;
  _fwd.subVectors(controls.target, camera.position); _fwd.y = 0;
  if (_fwd.lengthSq() < 1e-9) return;
  _fwd.normalize();
  _right.crossVectors(_fwd, _up).normalize();
  _delta.set(0, 0, 0);
  if (panKeys.has('fwd'))   _delta.add(_fwd);
  if (panKeys.has('back'))  _delta.sub(_fwd);
  if (panKeys.has('right')) _delta.add(_right);
  if (panKeys.has('left'))  _delta.sub(_right);
  if (_delta.lengthSq() === 0) return;
  // Pan eases down as you zoom in (slower the closer you get), floored at 25% of
  // full-view speed so it never crawls; capped at full-view speed when zoomed out.
  const liveDist = camera.position.distanceTo(controls.target);
  const effDist = Math.max(Math.min(liveDist, store.panRefDist), store.panRefDist * 0.25);
  const speed = 1.4 * effDist;
  _delta.normalize().multiplyScalar(speed * dt);
  camera.position.add(_delta);
  controls.target.add(_delta);
}
