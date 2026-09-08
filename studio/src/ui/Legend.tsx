import { useStudioStore } from '../state/studioStore';
import { legendRows, type FaceColorContext } from '../domain/terrainColors';

// Navmesh colour legend (#legend) — top 24 face-id/island keys by count.
export function Legend() {
  const mesh = useStudioStore((s) => s.mesh);
  const colorMode = useStudioStore((s) => s.colorMode);
  const isCampaign = useStudioStore((s) => s.isCampaign);
  const selection = useStudioStore((s) => s.selection);

  if (!mesh) return <div id="legend" />;
  const ctx: FaceColorContext = { colorMode, isCampaign, faceId: mesh.face_id, sceneLevelMask: mesh.scene_level_mask, selection };
  const { rows, overflow } = legendRows(ctx);
  return (
    <div id="legend">
      {rows.map((r) => (
        <div className="leg" key={r.key}>
          <span className="sw" style={{ background: r.swatch }} />
          {r.label} &times; {r.count}
        </div>
      ))}
      {overflow && <div className="leg">…</div>}
    </div>
  );
}
