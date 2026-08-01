// The shared hover tooltip (#tip) is written imperatively — like the original —
// so high-frequency pointermove updates never churn React. <Tip/> renders the
// empty styled element; interaction code calls these to fill it.
let el: HTMLElement | null = null;

function node(): HTMLElement | null {
  if (!el) el = document.getElementById('tip');
  return el;
}

export const tip = {
  show(text: string, clientX: number, clientY: number) {
    const t = node();
    if (!t) return;
    t.textContent = text;
    t.style.display = 'block';
    t.style.left = clientX + 14 + 'px';
    t.style.top = clientY + 10 + 'px';
  },
  hide() {
    const t = node();
    if (t) t.style.display = 'none';
  },
};
