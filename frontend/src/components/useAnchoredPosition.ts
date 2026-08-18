import { useCallback, useEffect, useRef, useState } from 'react';

export type CalloutPlacement = 'left' | 'right' | 'above' | 'below';

export interface AnchorRect {
  top: number;
  left: number;
  width: number;
  height: number;
  placement: CalloutPlacement;
}

export const CALLOUT_WIDTH = 320;
export const CALLOUT_GAP = 12;
/** Enough room for a callout of a few lines; below this we stop placing vertically. */
const CALLOUT_HEIGHT_ALLOWANCE = 190;
const HIGHLIGHT_CLASS = 'am-tour-target';

const prefersReducedMotion = (): boolean =>
  globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/**
 * Selector for a step's target.
 *
 * Escaped because one target id embeds a user-supplied project name, and an
 * unescaped quote in it makes querySelector throw rather than return null.
 */
export function targetSelector(testId: string): string {
  // Called through CSS so it keeps its receiver — a detached reference throws
  // "'escape' called on an object that is not a valid instance of CSS".
  const escaped = globalThis.CSS?.escape
    ? globalThis.CSS.escape(testId)
    : testId.replace(/["\\]/g, String.raw`\$&`);
  return `[data-testid="${escaped}"]`;
}

/**
 * Choose which side of the target the callout sits on.
 *
 * Sideways first, and that is the whole point: every step points at the button
 * that advances it, those buttons sit at the bottom of a form, and a callout
 * placed below one covers the form fields underneath. Beside it covers nothing.
 *
 * Right before left, because on these screens the right column is open space
 * next to the summary card, while the left is the form itself.
 *
 * Vertical placement is the fallback for targets with no horizontal room.
 */
export function choosePlacement(
  box: { top: number; left: number; right: number; bottom: number },
  viewport: { width: number; height: number },
): CalloutPlacement {
  const needed = CALLOUT_WIDTH + CALLOUT_GAP * 2;
  if (viewport.width - box.right >= needed) return 'right';
  if (box.left >= needed) return 'left';
  if (viewport.height - box.bottom >= CALLOUT_HEIGHT_ALLOWANCE) return 'below';
  return 'above';
}

const sameRect = (a: AnchorRect | null, b: AnchorRect | null): boolean => {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.top === b.top &&
    a.left === b.left &&
    a.width === b.width &&
    a.height === b.height &&
    a.placement === b.placement
  );
};

/**
 * Track the on-screen position of the element carrying `data-testid={testId}`,
 * and mark it as the tour's current target.
 *
 * The highlight is an outline on the target element itself, never an overlay
 * positioned over it — an overlay would intercept the very click the step is
 * asking the user to make, and would hide the control from assistive tech.
 *
 * Returns null while the target is absent, which is how the caller knows to
 * offer a way to navigate to it rather than pointing at nothing.
 */
export function useAnchoredPosition(testId: string | null): AnchorRect | null {
  const [rect, setRect] = useState<AnchorRect | null>(null);
  // The element currently wearing the highlight. Steps frequently activate
  // before their target exists — `resolve-pr` starts while the campaigns panel
  // is still fetching — so the element has to be re-resolved as the DOM
  // settles, not captured once when the effect runs.
  const highlighted = useRef<HTMLElement | null>(null);

  const sync = useCallback((): void => {
    const element = testId
      ? document.querySelector<HTMLElement>(targetSelector(testId))
      : null;

    if (element !== highlighted.current) {
      highlighted.current?.classList.remove(HIGHLIGHT_CLASS);
      highlighted.current = element;
      if (element) {
        element.classList.add(HIGHLIGHT_CLASS);
        if (!isInViewport(element)) {
          element.scrollIntoView({
            behavior: prefersReducedMotion() ? 'auto' : 'smooth',
            block: 'center',
          });
        }
      }
    }

    if (!element) {
      setRect((previous) => (previous === null ? previous : null));
      return;
    }

    const box = element.getBoundingClientRect();
    const next: AnchorRect = {
      top: box.top,
      left: box.left,
      width: box.width,
      height: box.height,
      placement: choosePlacement(box, {
        width: globalThis.innerWidth,
        height: globalThis.innerHeight,
      }),
    };
    // Only re-render when something actually moved. The observer below sees
    // every DOM change in the app, and a fresh object each time would re-render
    // the callout continuously while a panel polls.
    setRect((previous) => (sameRect(previous, next) ? previous : next));
  }, [testId]);

  useEffect(() => {
    let frame = 0;
    // Coalesce bursts: a single re-render of a list fires the observer many
    // times, and one measurement per frame is enough to look immediate.
    const schedule = (): void => {
      if (frame) return;
      frame = globalThis.requestAnimationFrame(() => {
        frame = 0;
        sync();
      });
    };

    sync();

    globalThis.addEventListener('resize', schedule);
    globalThis.addEventListener('scroll', schedule, true);

    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      if (frame) globalThis.cancelAnimationFrame(frame);
      highlighted.current?.classList.remove(HIGHLIGHT_CLASS);
      highlighted.current = null;
      globalThis.removeEventListener('resize', schedule);
      globalThis.removeEventListener('scroll', schedule, true);
      observer.disconnect();
    };
  }, [sync]);

  return rect;
}

function isInViewport(element: HTMLElement): boolean {
  const box = element.getBoundingClientRect();
  return box.top >= 0 && box.bottom <= globalThis.innerHeight;
}
