import { describe, expect, it } from 'vitest';
import { sceneLevelLabel, visibleInLevels, CAMPAIGN_REQUIRED_LEVELS } from './sceneLevels';
import { buildNavmesh } from '../scene/builders';
import type { MeshResponse } from './types';
import * as THREE from 'three';

describe('native scene visibility', () => {
  it('distinguishes Skye from Native campaign and level_3 variants', () => {
    for (const mask of [-109, -101, -69, -1]) expect(visibleInLevels(mask, CAMPAIGN_REQUIRED_LEVELS)).toBe(true);
    for (const mask of [-204, -203, -103]) expect(visibleInLevels(mask, CAMPAIGN_REQUIRED_LEVELS)).toBe(false);
    expect(visibleInLevels(-204, 16)).toBe(true);
    expect(sceneLevelLabel(-109, true)).toBe('-109 (base, level_1, civilian)');
    expect(sceneLevelLabel(-204, true)).toBe('-204 (level_2, civilian, siege)');
    expect(sceneLevelLabel(-204, false)).toBe('-204 (0xffffff34)');
  });

  it('filters faces and edges while keeping original pick indices and source data', () => {
    const mesh: MeshResponse = { vertices: [0,0,0, 1,0,0, 0,1,0, 3,0,0, 4,0,0, 3,1,0],
      faces: [[0,1,2], [3,4,5]], face_id: [1,7], scene_level_mask: [-204,-109] };
    const original = JSON.stringify(mesh);
    const filtered = buildNavmesh(mesh, new Set(), 'terrain', true, CAMPAIGN_REQUIRED_LEVELS);
    expect(filtered.triToFace).toEqual([1]);
    const edges = filtered.group.children[1] as THREE.LineSegments;
    expect(edges.geometry.attributes.position.count).toBe(6);
    const all = buildNavmesh(mesh, new Set(), 'terrain', true);
    expect(all.triToFace).toEqual([0,1]);
    expect(JSON.stringify(mesh)).toBe(original);
  });
});
