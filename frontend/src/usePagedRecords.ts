import { useEffect, useState } from 'react';
import { api } from './api';
export type Page<T> = { items: T[]; next_cursor: string | null };

export function usePagedRecords<T>(
  path: string,
  active: boolean,
  revision: number,
) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [result, setResult] = useState<{
    path: string;
    page: Page<T>;
    error: string;
    loading: boolean;
  }>({
    path: '',
    page: { items: [], next_cursor: null },
    error: '',
    loading: false,
  });
  useEffect(() => {
    setCursor(null);
  }, [path, revision]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let current = true;
    setResult((r) => ({ ...r, loading: true, error: '' }));
    const url =
      path +
      (path.includes('?') ? '&' : '?') +
      'limit=100' +
      (cursor ? '&cursor=' + encodeURIComponent(cursor) : '');
    api<Page<T>>(url, 'GET', undefined, controller.signal)
      .then((page) => {
        if (current) setResult({ path, page, error: '', loading: false });
      })
      .catch((e) => {
        if (current)
          setResult({
            path,
            page: { items: [], next_cursor: null },
            error: e.message,
            loading: false,
          });
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [path, cursor, active, revision]);
  const page =
    result.path === path ? result.page : { items: [], next_cursor: null };
  return {
    ...page,
    loading: result.loading,
    error: result.error,
    next: () => setCursor(page.next_cursor),
    first: () => setCursor(null),
    hasPrevious: cursor !== null,
  };
}
