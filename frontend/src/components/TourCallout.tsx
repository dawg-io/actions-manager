/* eslint-disable no-restricted-syntax, no-restricted-imports -- positions are computed at runtime and cannot be Tailwind classes; CSS import matches the existing component-stylesheet pattern */
import React from 'react';
import { Button } from './ui/button';
import {
  useAnchoredPosition,
  CALLOUT_GAP,
  CALLOUT_WIDTH,
  type AnchorRect,
} from './useAnchoredPosition';
import '../styles/OnboardingTour.css';

export interface TourCalloutProps {
  /** data-testid of the control that advances this step. */
  targetTestId: string;
  title: string;
  body: string;
  /** 1-based position, used for the "Step N of M" label. */
  stepNumber: number;
  totalSteps: number;
  onSkip: () => void;
  /**
   * Where the target lives. Omitted — or equal to the current location — means
   * there is nowhere useful to send the user, and no navigate action is shown.
   */
  onNavigate?: () => void;
  navigateLabel?: string;
  /** Shown in place of the body when the target is not on this screen. */
  awayMessage?: string;
}

/** Pin the callout inside the viewport on both axes. */
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, max));
}

/**
 * Turn the anchor into fixed-position styles.
 *
 * `height` is the callout's real measured height. Without it the vertical
 * clamp can only pin the *top* on screen, which is what let the callout run
 * off the bottom next to a button near the foot of a form — the top was
 * legal, the bottom was not.
 */
export function positionFor(anchor: AnchorRect | null, height: number): React.CSSProperties {
  if (!anchor) {
    // Nothing to point at: park it out of the way rather than over the page.
    return { bottom: CALLOUT_GAP * 2, left: CALLOUT_GAP * 2 };
  }

  const maxLeft = Math.max(CALLOUT_GAP, globalThis.innerWidth - CALLOUT_WIDTH - CALLOUT_GAP);
  const maxTop = Math.max(CALLOUT_GAP, globalThis.innerHeight - height - CALLOUT_GAP);

  if (anchor.placement === 'left' || anchor.placement === 'right') {
    const left =
      anchor.placement === 'left'
        ? anchor.left - CALLOUT_WIDTH - CALLOUT_GAP
        : anchor.left + anchor.width + CALLOUT_GAP;
    return {
      left: clamp(left, CALLOUT_GAP, maxLeft),
      // Centred on the target so the arrow lines up with the button, then
      // pushed back on screen if that would hang off either edge.
      top: clamp(anchor.top + anchor.height / 2 - height / 2, CALLOUT_GAP, maxTop),
    };
  }

  const left = clamp(anchor.left, CALLOUT_GAP, maxLeft);
  return anchor.placement === 'above'
    ? { left, top: clamp(anchor.top - height - CALLOUT_GAP, CALLOUT_GAP, maxTop) }
    : { left, top: clamp(anchor.top + anchor.height + CALLOUT_GAP, CALLOUT_GAP, maxTop) };
}

const TourCallout: React.FC<TourCalloutProps> = ({
  targetTestId,
  title,
  body,
  stepNumber,
  totalSteps,
  onSkip,
  onNavigate,
  navigateLabel = 'Take me there',
  awayMessage = 'This step happens on another screen.',
}) => {
  const anchor = useAnchoredPosition(targetTestId);
  const calloutRef = React.useRef<HTMLElement | null>(null);
  const [height, setHeight] = React.useState(0);

  // Measure after paint so the clamp uses the height this body actually
  // renders at, rather than an assumed one. Step bodies differ in length, so
  // a fixed guess is wrong for most of them.
  React.useLayoutEffect(() => {
    const measured = calloutRef.current?.offsetHeight ?? 0;
    if (measured && measured !== height) setHeight(measured);
  }, [title, body, anchor, height]);

  // Escape dismisses from any step, matching the dialog convention elsewhere —
  // but only when nothing else owns the key. This callout is non-modal and
  // several steps point at a control inside a dialog, so a bare listener would
  // read "Escape to close this modal" as "end the tour", permanently, with no
  // replay entry point to recover through.
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return;
      if (document.querySelector('[role="dialog"][data-state="open"]')) return;
      onSkip();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onSkip]);

  return (
    <aside
      aria-label={`Onboarding step ${stepNumber} of ${totalSteps}`}
      className="am-tour-callout"
      data-placement={anchor?.placement ?? 'none'}
      data-testid="tour-callout"
      ref={calloutRef}
      style={positionFor(anchor, height)}
    >
      {/* Non-modal by design: no overlay, no focus trap, nothing captured.
          The app stays fully usable while this is on screen — which is the
          whole point, since every step is a real action the user performs. */}
      <p aria-live="polite" className="am-tour-callout-progress">
        Step {stepNumber} of {totalSteps}
      </p>
      <p className="am-tour-callout-title">{title}</p>
      <p className="am-tour-callout-body">{anchor ? body : awayMessage}</p>

      <div className="am-tour-callout-actions">
        <Button data-testid="tour-callout-skip" onClick={onSkip} size="sm" variant="ghost">
          Skip tour
        </Button>
        {/* Only offered when it actually goes somewhere. A button that
            navigates to the route you are already on does nothing, which is
            worse than no button. */}
        {!anchor && onNavigate && (
          <Button data-testid="tour-callout-navigate" onClick={onNavigate} size="sm">
            {navigateLabel}
          </Button>
        )}
      </div>
    </aside>
  );
};

export default TourCallout;
