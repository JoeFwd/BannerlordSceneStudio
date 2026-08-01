import { useEntitiesStore } from '../state/entitiesStore';
import type { Settlement } from '../domain/types';

// #entinfo — the movable/water/part-land/moved counts. Reads the (in-place mutated)
// settlement records; re-renders when movedCount / moveInfo change during a drag.
export function EntInfo() {
  const settlements = useEntitiesStore((s) => s.settlements);
  const movedCount = useEntitiesStore((s) => s.movedCount);
  const moveInfo = useEntitiesStore((s) => s.moveInfo);

  let text: string;
  if (!settlements.length) {
    text = 'no settlements';
  } else {
    const mv = settlements.filter((m) => m.movable);
    const wet = mv.filter((m) => !m.on_land).length;
    const part = mv.filter((m) => {
      const f = m.land_fraction;
      return f != null && f > 0 && f < 0.999;
    }).length;
    text = `${mv.length} movable · ${wet} in water · ${part} part-land · ${movedCount} moved`
      + (moveInfo ? `\n${moveInfo}` : '');
  }
  return (
    <div id="entinfo" style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12, color: '#d4c99f', marginTop: 6 }}>
      {text}
    </div>
  );
}

export function saveEntLabel(movedCount: number): string {
  return movedCount ? `Save placements (${movedCount})` : 'Save placements';
}

// #selinfoEnt — the selected settlement readout.
function selText(ent: Settlement | null): string {
  if (!ent) return 'no settlement selected';
  const rad = ent.radius != null ? ent.radius.toFixed(3) : '(no zone)';
  return `${ent.name}\n${ent.type || '?'} · radius ${rad}\n`
    + `${ent.x.toFixed(1)}, ${ent.y.toFixed(1)} · ${ent.on_land ? 'land' : 'WATER'}`;
}

export function SelInfoEnt() {
  const selectedEnt = useEntitiesStore((s) => s.selectedEnt);
  return (
    <div id="selinfoEnt" style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12, color: '#9fd4c9', marginTop: 8 }}>
      {selText(selectedEnt)}
    </div>
  );
}
