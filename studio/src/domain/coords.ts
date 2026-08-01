// Bannerlord is Z-up; three.js is Y-up. World (x,y,z) -> three (x, z, -y).
export const W2T = (x: number, y: number, z: number): [number, number, number] => [x, z, -y];

// Inverse used when reading a ground-raycast hit back to world XY:
// three (X, _, Z) -> world (x, y) = (X, -Z).
export const T2W_XY = (X: number, Z: number): [number, number] => [X, -Z];
