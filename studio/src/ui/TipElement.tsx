// The hover tooltip element. Rendered empty and styled; filled imperatively by
// ui/tip.ts so high-frequency pointermove updates never churn React.
export function Tip() {
  return <div id="tip" />;
}
