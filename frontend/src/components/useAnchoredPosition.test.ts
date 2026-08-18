import { choosePlacement, targetSelector, CALLOUT_WIDTH, CALLOUT_GAP } from './useAnchoredPosition';

const VIEWPORT = { width: 1400, height: 900 };
// Centred target: enough room on both sides, so preference is what decides.
const box = (over: Partial<{ top: number; left: number; right: number; bottom: number }> = {}) => ({
  top: 400,
  left: 600,
  right: 700,
  bottom: 440,
  ...over,
});

describe('choosePlacement', () => {
  test('prefers the right when both sides fit', () => {
    // The right column is open space beside the summary card; the left is the
    // form itself, so a callout there covers what the user is reading.
    expect(choosePlacement(box(), VIEWPORT)).toBe('right');
  });

  test('uses the left when the target is hard against the right edge', () => {
    expect(choosePlacement(box({ left: 1250, right: 1390 }), VIEWPORT)).toBe('left');
  });

  test('falls back to below when neither side has room', () => {
    const narrow = { width: CALLOUT_WIDTH + 40, height: 900 };
    expect(choosePlacement(box({ left: 20, right: narrow.width - 20 }), narrow)).toBe('below');
  });

  test('flips above when there is no room below either', () => {
    const narrow = { width: CALLOUT_WIDTH + 40, height: 500 };
    expect(
      choosePlacement(box({ top: 430, left: 20, right: narrow.width - 20, bottom: 470 }), narrow),
    ).toBe('above');
  });

  test('needs a full callout plus gaps before choosing a side', () => {
    // Exactly enough room on the right fits; one pixel less falls back to left.
    const needed = CALLOUT_WIDTH + CALLOUT_GAP * 2;
    expect(
      choosePlacement(box({ left: 500, right: VIEWPORT.width - needed }), VIEWPORT),
    ).toBe('right');
    expect(
      choosePlacement(box({ left: 500, right: VIEWPORT.width - needed + 1 }), VIEWPORT),
    ).toBe('left');
  });
});

describe('targetSelector', () => {
  test('escapes a project name so querySelector cannot throw', () => {
    // One step's target id embeds the user's project name, which is only
    // trimmed server-side. A quote in it turned a miss into a SyntaxError
    // thrown from the mount effect and from every observer callback after.
    const selector = targetSelector('project-row-My "Demo"');

    expect(() => document.querySelector(selector)).not.toThrow();
    expect(document.querySelector(selector)).toBeNull();
  });

  test('leaves an ordinary id usable', () => {
    const selector = targetSelector('wizard-continue');
    const el = document.createElement('button');
    el.dataset.testid = 'wizard-continue';
    document.body.appendChild(el);

    try {
      expect(document.querySelector(selector)).toBe(el);
    } finally {
      el.remove();
    }
  });
});
