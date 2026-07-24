import { useEffect, useMemo, useState } from "react";

export type PageSize = number | "all";
export const PAGE_SIZE_OPTIONS: PageSize[] = [5, 10, 25, 50, "all"];

export interface UsePagedListResult<T> {
  pageItems: T[];
  page: number;
  pageSize: PageSize;
  totalPages: number;
  totalItems: number;
  setPage: (page: number) => void;
  setPageSize: (size: PageSize) => void;
}

export const usePagedList = <T,>(items: T[], defaultPageSize: PageSize = 5): UsePagedListResult<T> => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(defaultPageSize);

  // items is a new array only when the underlying data/filters actually change,
  // so this doubles as the "filters changed" and "list shrank" reset signal.
  useEffect(() => {
    setPage(1);
  }, [items]);

  const totalItems = items.length;
  const totalPages = pageSize === "all" ? 1 : Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(page, totalPages);

  const pageItems = useMemo(() => {
    if (pageSize === "all") return items;
    const start = (safePage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, pageSize, safePage]);

  const handleSetPageSize = (size: PageSize) => {
    setPageSize(size);
    setPage(1);
  };

  return { pageItems, page: safePage, pageSize, totalPages, totalItems, setPage, setPageSize: handleSetPageSize };
};
