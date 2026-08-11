import { renderHook, act } from '@testing-library/react';
import { useUnifiedWorkflowsState } from './useUnifiedWorkflowsState';

const renderState = () =>
  renderHook(() => useUnifiedWorkflowsState([], jest.fn(), jest.fn()));

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
    const getItem = jest
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('storage blocked');
      });

    expect(() => renderState()).not.toThrow();
    expect(renderState().result.current.isCollapsed).toBe(false);

    getItem.mockRestore();
  });
});
