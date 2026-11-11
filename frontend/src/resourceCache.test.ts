import { expect, it, vi } from 'vitest';
import { invalidateResources, sharedRead } from './resourceCache';

it('deduplicates reads and gives each subscriber cancellation ownership', async () => {
  let finish: (value: number) => void = () => {};
  let underlying: AbortSignal | undefined;
  const fetcher = vi.fn((signal: AbortSignal) => {
    underlying = signal;
    return new Promise<number>((resolve) => {
      finish = resolve;
    });
  });
  const first = new AbortController();
  const a = sharedRead('/forecast?month=2026-01', first.signal, fetcher);
  const b = sharedRead('/forecast?month=2026-01', undefined, fetcher);
  expect(fetcher).toHaveBeenCalledTimes(1);
  first.abort();
  await expect(a).rejects.toMatchObject({ name: 'AbortError' });
  expect(underlying?.aborted).toBe(false);
  finish(42);
  expect(await b).toBe(42);
  expect(await sharedRead('/forecast?month=2026-01', undefined, fetcher)).toBe(
    42,
  );
  invalidateResources('/transactions/new');
  const next = vi.fn(async () => 99);
  expect(await sharedRead('/forecast?month=2026-01', undefined, next)).toBe(99);
});

it('retains unrelated metadata after a transaction mutation', async () => {
  const settings = vi.fn(async () => 'USD');
  await sharedRead('/settings', undefined, settings);
  invalidateResources('/transactions/new');
  await sharedRead('/settings', undefined, settings);
  expect(settings).toHaveBeenCalledTimes(1);
});
