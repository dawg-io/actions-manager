import { positionFor } from './TourCallout';
import { CALLOUT_GAP, type AnchorRect } from './useAnchoredPosition';

const anchor = (over: Partial<AnchorRect> = {}): AnchorRect => ({
  top: 1060,
  left: 1450,
  width: 130,
  height: 40,
  placement: 'left',
  ...over,
});

describe('positionFor', () => {
  const originalHeight = globalThis.innerHeight;
  const originalWidth = globalThis.innerWidth;

  beforeEach(() => {
    Object.defineProperty(globalThis, 'innerHeight', { value: 1200, configurable: true });
    Object.defineProperty(globalThis, 'innerWidth', { value: 2000, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'innerHeight', { value: originalHeight, configurable: true });
    Object.defineProperty(globalThis, 'innerWidth', { value: originalWidth, configurable: true });
  });

  test('keeps the callout on screen beside a button near the bottom', () => {
    // The reported defect: Continue sits near the foot of the wizard, so a
    // callout centred on it ran off the bottom and its text was cut off.
    const style = positionFor(anchor(), 260);

    const top = style.top as number;
    expect(top + 260).toBeLessThanOrEqual(1200);
    expect(top).toBeGreaterThanOrEqual(CALLOUT_GAP);
  });

  test('centres on the target when there is room to do so', () => {
    const style = positionFor(anchor({ top: 500 }), 200);

    // 500 + 40/2 - 200/2 = 420
    expect(style.top).toBe(420);
  });

  test('a callout taller than the viewport is pinned to the top, not pushed off', () => {
    const style = positionFor(anchor(), 5000);

    expect(style.top).toBe(CALLOUT_GAP);
  });

  test('never overflows the right edge', () => {
    const style = positionFor(anchor({ placement: 'right', left: 1900, width: 80 }), 200);

    expect(style.left as number).toBeLessThanOrEqual(2000 - 320 - CALLOUT_GAP);
  });

  test('an above placement sits above the target and stays on screen', () => {
    const style = positionFor(anchor({ placement: 'above', top: 800 }), 200);

    expect(style.top).toBe(800 - 200 - CALLOUT_GAP);
  });

  test('parks out of the way when there is nothing to point at', () => {
    const style = positionFor(null, 200);

    expect(style.bottom).toBe(CALLOUT_GAP * 2);
    expect(style.top).toBeUndefined();
  });
});
