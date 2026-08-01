import { useEffect, useMemo } from 'react';
import { useStudioStore } from '../state/studioStore';
import { buildTerrainMesh } from './builders';
import { sceneRefs } from './sceneRefs';

// The heightmap surface. Also the raycast target when dragging a settlement, so
// it registers itself in sceneRefs for the drag handler to reach.
export function Terrain() {
  const terrain = useStudioStore((s) => s.terrain);
  const visible = useStudioStore((s) => s.terrainVisible);
  const mesh = useMemo(() => (terrain ? buildTerrainMesh(terrain) : null), [terrain]);

  useEffect(() => {
    sceneRefs.terrainMesh = mesh;
    return () => {
      if (sceneRefs.terrainMesh === mesh) sceneRefs.terrainMesh = null;
    };
  }, [mesh]);

  if (!mesh) return null;
  mesh.visible = visible;
  return <primitive object={mesh} />;
}
