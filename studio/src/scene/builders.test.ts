import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { buildNavmesh } from './builders';
import { W2T } from '../domain/coords';
import { NAVMESH_LIFT } from '../domain/constants';
import type { MeshResponse } from '../domain/types';

function fixture(vertices: number[], faces: number[][]) {
  const mesh: MeshResponse = { vertices, faces, face_id: faces.map(() => 1), group: faces.map(() => 0) };
  const before = JSON.stringify(mesh);
  const built = buildNavmesh(mesh, new Set(), 'terrain', true);
  const edges = built.group.children[1] as THREE.LineSegments;
  const points = edges.geometry.attributes.position;
  const segments = [];
  for (let i = 0; i < points.count; i += 2) {
    segments.push([[points.getX(i), points.getY(i), points.getZ(i)],
      [points.getX(i + 1), points.getY(i + 1), points.getZ(i + 1)]]);
  }
  expect(JSON.stringify(mesh)).toBe(before);
  return { built, segments };
}

describe('navmesh source polygon edges', () => {
  it('draws four boundary edges and no triangulation diagonal on a warped quad', () => {
    const vertices = [0, 0, 0, 2, 0, 0, 2, 2, 1, 0, 2, 0];
    const { built, segments } = fixture(vertices, [[0, 1, 2, 3]]);
    expect(segments).toHaveLength(4);
    for (let k = 0; k < 4; k++) {
      for (let end = 0; end < 2; end++) {
        const id = (k + end) % 4;
        const expected = W2T(vertices[id * 3], vertices[id * 3 + 1], vertices[id * 3 + 2] + NAVMESH_LIFT);
        expected.forEach((value, axis) => expect(segments[k][end][axis]).toBeCloseTo(value, 5));
      }
    }
    expect(built.triToFace).toEqual([0, 0]);
  });

  it('preserves the shared edge of coplanar quads, drawing it only once', () => {
    const { segments, built } = fixture(
      [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 2, 0, 0, 2, 1, 0],
      [[0, 1, 2, 3], [1, 4, 5, 2]],
    );
    expect(segments).toHaveLength(7);
    expect(built.triToFace).toEqual([0, 0, 1, 1]);
  });

  it('retains a real diagonal when it separates two source triangle faces', () => {
    const { segments, built } = fixture([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], [[0, 1, 2], [0, 2, 3]]);
    expect(segments).toHaveLength(5);
    expect(built.triToFace).toEqual([0, 1]);
  });
});
