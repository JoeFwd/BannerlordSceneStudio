import { beforeEach, expect, it } from 'vitest';
import { useStudioStore } from './studioStore';

beforeEach(() => {
  useStudioStore.setState({
    selection: new Set(), faceId: '0', sceneLevelMask: '',
    mesh: { vertices: [], faces: [[], []], face_id: [1, 7], scene_level_mask: [-109, -1] },
  });
});

it('keeps mixed visibility masks and restores the remaining face attributes on deselection', () => {
  const select = useStudioStore.getState().selectFaceAt;
  select(0, false);
  expect(useStudioStore.getState().sceneLevelMask).toBe('-109');
  select(1, true);
  expect(useStudioStore.getState().sceneLevelMask).toBe('');
  select(0, true);
  expect([...useStudioStore.getState().selection]).toEqual([1]);
  expect(useStudioStore.getState().faceId).toBe('7');
  expect(useStudioStore.getState().sceneLevelMask).toBe('-1');
});
