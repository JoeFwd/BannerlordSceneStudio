// Keyboard pan by physical key position (event.code), so WASD (QWERTY) and ZQSD
// (AZERTY) and the arrows all drive the same directions.
export type PanToken = 'fwd' | 'back' | 'left' | 'right';

export function panToken(code: string): PanToken | null {
  switch (code) {
    case 'KeyW': case 'ArrowUp': return 'fwd';
    case 'KeyS': case 'ArrowDown': return 'back';
    case 'KeyA': case 'ArrowLeft': return 'left';
    case 'KeyD': case 'ArrowRight': return 'right';
  }
  return null;
}

// Pan eases down as you zoom in (slower the closer you get), floored at 25% of
// full-view speed so it never crawls; capped at full-view speed when zoomed out.
export function effectiveDist(liveDist: number, panRefDist: number): number {
  return Math.max(Math.min(liveDist, panRefDist), panRefDist * 0.25);
}

export function panSpeed(effDist: number): number {
  return 1.4 * effDist;
}
