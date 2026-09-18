import { renderHook, act } from '@testing-library/react';
import { useUnifiedWorkflowsState } from './useUnifiedWorkflowsState';

const renderState = () =>
  renderHook(() => useUnifiedWorkflowsState([], vi.fn(), vi.fn()));

beforeEach(() => {
  localStorage.clear();
});

describe('useUnifiedWorkflowsState — Project Files panel collapse persistence', () => {
  it('starts expanded when nothing is stored', () => {
    const { result } = renderState();

    expect(result.current.isCollapsed).toBe(false);
  });

  it('starts collapsed when the stored preference says so', () => {
    localStorage.setItem('projectFiles.collapsed', 'true');

    const { result } = renderState();

    expect(result.current.isCollapsed).toBe(true);
  });

  it('persists the collapsed state so it survives a remount', () => {
    const first = renderState();

    act(() => first.result.current.setIsCollapsed(true));
    expect(localStorage.getItem('projectFiles.collapsed')).toBe('true');
    first.unmount();

    const { result } = renderState();
    expect(result.current.isCollapsed).toBe(true);
  });

  it('persists expanding again', () => {
    localStorage.setItem('projectFiles.collapsed', 'true');
    const { result } = renderState();

    act(() => result.current.setIsCollapsed(false));

    expect(localStorage.getItem('projectFiles.collapsed')).toBe('false');
  });

  it('treats an unrecognised stored value as expanded', () => {
    localStorage.setItem('projectFiles.collapsed', 'garbage');

    const { result } = renderState();

    expect(result.current.isCollapsed).toBe(false);
  });

  it('falls back to expanded when storage is unavailable', () => {
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('storage blocked');
      });

    expect(() => renderState()).not.toThrow();
    expect(renderState().result.current.isCollapsed).toBe(false);

    getItem.mockRestore();
  });
});

describe('markWorkflowAsSaved does not replay a stale workflows array', () => {
  /**
   * Renaming from the editor applies the new name and saves in the same tick.
   * The save resolves later and calls markWorkflowAsSaved, which used to build
   * its next array from `workflows` captured in the callback's closure — the
   * array as it was *before* the rename. Writing that back reverted the name in
   * the UI and stamped savedName with the name the user had just replaced, so
   * the rename appeared to undo itself a moment after being confirmed.
   *
   * Driven through the real setter contract: a functional updater is handed the
   * latest array, a direct one is not.
   */
  const run = (type: 'regular' | 'reusable') => {
    const initial = [{ name: 'ci', savedName: 'ci', isModified: true }];
    let current = initial;
    const setWorkflows = vi.fn((next: any) => {
      current = typeof next === 'function' ? next(current) : next;
    });

    const { result } = renderHook(() =>
      useUnifiedWorkflowsState(
        initial,
        type === 'regular' ? setWorkflows : vi.fn(),
        type === 'reusable' ? setWorkflows : vi.fn(),
      )
    );

    // The rename lands first, exactly as handleWorkflowChange applies it.
    current = [{ ...current[0], name: 'ci-v2' }];
    act(() => result.current.markWorkflowAsSaved(0, type, 'committed_locally'));

    return current[0];
  };

  it('keeps the renamed name for a regular workflow', () => {
    const saved = run('regular');

    expect(saved.name).toBe('ci-v2');
    expect(saved.savedName).toBe('ci-v2');
    expect(saved.isModified).toBe(false);
  });

  it('keeps the renamed name for a reusable workflow', () => {
    const saved = run('reusable');

    expect(saved.name).toBe('ci-v2');
    expect(saved.savedName).toBe('ci-v2');
  });
});
