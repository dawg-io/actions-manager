import { TourSignals, tour } from './tour';

describe('TourSignals restart', () => {
  afterEach(() => {
    tour.demoProjectName = null;
  });

  test('notifies every subscriber that a restart was asked for', () => {
    const signals = new TourSignals();
    const a = vi.fn();
    const b = vi.fn();
    signals.onRestartRequested(a);
    signals.onRestartRequested(b);

    signals.requestRestart();

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  test('unsubscribing stops delivery', () => {
    const signals = new TourSignals();
    const listener = vi.fn();
    const unsubscribe = signals.onRestartRequested(listener);

    unsubscribe();
    signals.requestRestart();

    expect(listener).not.toHaveBeenCalled();
  });

  test('forgets the project from the previous run', () => {
    // Otherwise the restarted tour points at a project the user made last
    // time, and its "open it to carry on" recovery is aimed at the wrong one.
    tour.demoProjectName = 'Demo-Project-2';

    tour.requestRestart();

    expect(tour.demoProjectName).toBeNull();
  });

  test('requesting a restart with no subscribers is harmless', () => {
    expect(() => new TourSignals().requestRestart()).not.toThrow();
  });
});
