import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { Account } from './api';

export function useCardFreshness(onUpdated: (cards: Account[]) => void) {
  const [error, setError] = useState('');
  const callback = useRef(onUpdated);
  useEffect(() => {
    callback.current = onUpdated;
  }, [onUpdated]);
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    // A focus/online event can coincide with the minute timer.
    if (controller.current) return;
    const request = new AbortController();
    controller.current = request;
    try {
      const cards = await api<Account[]>(
        '/accounts',
        'GET',
        undefined,
        request.signal,
      );
      if (!request.signal.aborted) {
        callback.current(cards);
        setError('');
      }
    } catch (e) {
      if (!request.signal.aborted && (e as Error).name !== 'AbortError')
        setError(
          'Could not refresh card freshness alerts. Retrying when the local server reconnects.',
        );
    } finally {
      if (controller.current === request) controller.current = null;
    }
  }, []);
  useEffect(() => {
    const timer = setInterval(() => void refresh(), 60000);
    const visible = () => {
      if (!document.hidden) void refresh();
    };
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('online', visible);
    window.addEventListener('focus', visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('online', visible);
      window.removeEventListener('focus', visible);
      controller.current?.abort();
      controller.current = null;
    };
  }, [refresh]);
  return { error, refresh };
}
