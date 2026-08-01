import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export const scene = new THREE.Scene();
scene.background = new THREE.Color(0x151515);
export const camera = new THREE.PerspectiveCamera(55, innerWidth/innerHeight, 0.5, 20000);
export const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
export const controls = new OrbitControls(camera, renderer.domElement);
controls.zoomSpeed = 2.0;   // faster wheel zoom
scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const sun = new THREE.DirectionalLight(0xffffff, 1.2); sun.position.set(1, 2, 1); scene.add(sun);
addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
