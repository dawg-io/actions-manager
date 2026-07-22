import { describe, test, expect, beforeEach, vi } from 'vitest';
import { ToastService } from './toast';

describe('ToastService', () => {
  let service: ToastService;

  beforeEach(() => {
    service = new ToastService();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test('success() adds a success toast', () => {
    const listener = vi.fn();
    service.subscribe(listener);
    listener.mockClear();

    service.success('Workflow saved');

    expect(listener).toHaveBeenCalledTimes(1);
    const [toasts] = listener.mock.calls[0];
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({ message: 'Workflow saved', type: 'success' });
  });

  test('error() adds an error toast', () => {
    const listener = vi.fn();
    service.subscribe(listener);
    listener.mockClear();

    service.error('Save failed');

    const [toasts] = listener.mock.calls[0];
    expect(toasts[0]).toMatchObject({ message: 'Save failed', type: 'error' });
  });

  test('dismiss() removes a toast by id', () => {
    const listener = vi.fn();
    service.subscribe(listener);
    listener.mockClear();

    service.success('hello');
    const id = listener.mock.calls[0][0][0].id;

    listener.mockClear();
    service.dismiss(id);

    const [toasts] = listener.mock.calls[0];
    expect(toasts).toHaveLength(0);
  });

  test('toast auto-dismisses after default duration', () => {
    const listener = vi.fn();
    service.subscribe(listener);
    listener.mockClear();

    service.success('Workflow saved');
    expect(listener.mock.calls[0][0]).toHaveLength(1);

    listener.mockClear();
    vi.advanceTimersByTime(4001);
    expect(listener.mock.calls[0][0]).toHaveLength(0);
  });

  describe('deduplication', () => {
    test('does not add a duplicate toast when the same message+type is already visible', () => {
      const listener = vi.fn();
      service.subscribe(listener);
      listener.mockClear();

      service.success("Workflow 'my-flow.yml' saved as draft.");
      service.success("Workflow 'my-flow.yml' saved as draft.");

      // Listener should have been called only once (first add), not twice
      expect(listener).toHaveBeenCalledTimes(1);
      const [toasts] = listener.mock.calls[0];
      expect(toasts).toHaveLength(1);
    });

    test('allows the same message after the first toast is dismissed', () => {
      const listener = vi.fn();
      service.subscribe(listener);
      listener.mockClear();

      service.success("Workflow 'my-flow.yml' saved as draft.");
      const id = listener.mock.calls[0][0][0].id;
      service.dismiss(id);

      listener.mockClear();
      service.success("Workflow 'my-flow.yml' saved as draft.");

      expect(listener).toHaveBeenCalledTimes(1);
      const [toasts] = listener.mock.calls[0];
      expect(toasts).toHaveLength(1);
    });

    test('allows a different message of the same type while one is visible', () => {
      const listener = vi.fn();
      service.subscribe(listener);
      listener.mockClear();

      service.success("Workflow 'a.yml' saved as draft.");
      service.success("Workflow 'b.yml' saved as draft.");

      // Two calls – second one is a different message so it should be added
      expect(listener).toHaveBeenCalledTimes(2);
      expect(listener.mock.calls[1][0]).toHaveLength(2);
    });

    test('allows the same message with a different type', () => {
      const listener = vi.fn();
      service.subscribe(listener);
      listener.mockClear();

      service.success('Operation completed');
      service.error('Operation completed');

      expect(listener).toHaveBeenCalledTimes(2);
      expect(listener.mock.calls[1][0]).toHaveLength(2);
    });
  });
});
