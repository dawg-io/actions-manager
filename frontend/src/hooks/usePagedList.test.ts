import { renderHook, act } from '@testing-library/react';
import { usePagedList } from './usePagedList';

describe('usePagedList', () => {
  test('defaults to a page size of 5', () => {
    const items = Array.from({ length: 12 }, (_, i) => i + 1);
    const { result } = renderHook(() => usePagedList(items));

    expect(result.current.pageSize).toBe(5);
    expect(result.current.pageItems).toEqual([1, 2, 3, 4, 5]);
    expect(result.current.totalPages).toBe(3);
  });

  test('setPage moves to the requested slice', () => {
    const items = Array.from({ length: 12 }, (_, i) => i + 1);
    const { result } = renderHook(() => usePagedList(items));

    act(() => result.current.setPage(2));

    expect(result.current.page).toBe(2);
    expect(result.current.pageItems).toEqual([6, 7, 8, 9, 10]);
  });

  test('setPageSize resets to page 1 and returns "all" items regardless of size', () => {
    const items = Array.from({ length: 12 }, (_, i) => i + 1);
    const { result } = renderHook(() => usePagedList(items));

    act(() => result.current.setPage(3));
    act(() => result.current.setPageSize(25));

    expect(result.current.page).toBe(1);
    expect(result.current.pageItems).toHaveLength(12);
    expect(result.current.totalPages).toBe(1);

    act(() => result.current.setPageSize('all'));

    expect(result.current.pageItems).toEqual(items);
    expect(result.current.totalPages).toBe(1);
  });

  test('clamps the current page when the underlying list shrinks', () => {
    let items = Array.from({ length: 12 }, (_, i) => i + 1);
    const { result, rerender } = renderHook(({ list }) => usePagedList(list), {
      initialProps: { list: items },
    });

    act(() => result.current.setPage(3));
    expect(result.current.page).toBe(3);

    items = [1, 2, 3];
    rerender({ list: items });

    expect(result.current.page).toBe(1);
    expect(result.current.pageItems).toEqual([1, 2, 3]);
  });

  test('resets to page 1 when a new array reference arrives, but not on an unchanged reference', () => {
    const items = Array.from({ length: 12 }, (_, i) => i + 1);
    const { result, rerender } = renderHook(({ list }) => usePagedList(list), {
      initialProps: { list: items },
    });

    act(() => result.current.setPage(2));
    expect(result.current.page).toBe(2);

    rerender({ list: items });
    expect(result.current.page).toBe(2);

    rerender({ list: [...items] });
    expect(result.current.page).toBe(1);
  });
});
