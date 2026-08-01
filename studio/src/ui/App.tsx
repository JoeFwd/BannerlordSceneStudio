import { useEffect } from 'react';
import { useStudioStore } from '../state/studioStore';
import { Studio } from '../scene/Studio';
import { Panel } from './Panel';
import { Tip } from './TipElement';

export function App() {
  const init = useStudioStore((s) => s.init);
  useEffect(() => { init(); }, [init]);

  return (
    <>
      <Panel />
      <Studio />
      <div id="hint">WASD/ZQSD or arrows = move &middot; drag = orbit &middot; wheel = zoom &middot; right-drag = pan</div>
      <Tip />
    </>
  );
}
