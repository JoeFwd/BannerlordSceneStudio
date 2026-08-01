import { useStudioStore } from '../state/studioStore';
import { faceLabel } from '../domain/terrainColors';

// Navmesh face selection readout (#selinfo).
export function SelInfo() {
  const selection = useStudioStore((s) => s.selection);
  const mesh = useStudioStore((s) => s.mesh);

  let text = 'none';
  if (selection.size) {
    const arr = [...selection];
    text = `${arr.length} face(s): [${arr.slice(0, 12).join(', ')}${arr.length > 12 ? '…' : ''}]`;
    if (mesh && mesh.face_id.length) {
      text += `\n${faceLabel(arr[0], { isCampaign: useStudioStore.getState().isCampaign, faceId: mesh.face_id, group: mesh.group })}`;
    }
  }
  return <div id="selinfo">{text}</div>;
}
