import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import type { Forecast } from './api';
import { useWorkspace } from './useWorkspace';
vi.mock('./api', () => ({ api: vi.fn() }));
const forecast = (month: string) =>
  ({
    month,
    income: 600000,
    expenses: 594367,
    remaining: 5633,
    deficit: false,
    lines: [],
    actual: {
      expenses: 0,
      status: 'missing',
      marked_complete: false,
      transaction_count: 0,
    },
    actual_deficit: false,
  }) satisfies Forecast;
beforeEach(() => vi.mocked(api).mockReset());
it('hides the prior month immediately and stays empty after the selected month fails', async () => {
  let rejectDecember: (reason: Error) => void = () => {};
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/forecast?month=2026-11') return forecast('2026-11');
    if (path === '/forecast?month=2026-12')
      return new Promise((_resolve, reject) => {
        rejectDecember = reject;
      });
    if (path === '/settings') return { currency: 'USD' };
    return [];
  });
  const { result, rerender } = renderHook(
    ({ month }) => useWorkspace(month, 0),
    { initialProps: { month: '2026-11' } },
  );
  await waitFor(() => expect(result.current.forecast?.month).toBe('2026-11'));
  rerender({ month: '2026-12' });
  expect(result.current.forecast).toBeNull();
  expect(result.current.loading).toBe(true);
  await act(async () => rejectDecember(new Error('December unavailable')));
  expect(result.current.forecast).toBeNull();
  expect(result.current.error).toBe('December unavailable');
  expect(result.current.loading).toBe(false);
  expect(
    vi.mocked(api).mock.calls.filter(([path]) => path === '/settings'),
  ).toHaveLength(1);
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path.startsWith('/trends')),
  ).toBe(false);
});
it('ignores a late response from an abandoned month', async () => {
  let finish: (value: unknown) => void = () => {};
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/forecast?month=2026-11')
      return new Promise((resolve) => {
        finish = resolve;
      });
    if (path === '/forecast?month=2026-12') return forecast('2026-12');
    return [];
  });
  const { result, rerender } = renderHook(
    ({ month }) => useWorkspace(month, 0),
    { initialProps: { month: '2026-11' } },
  );
  rerender({ month: '2026-12' });
  await waitFor(() => expect(result.current.forecast?.month).toBe('2026-12'));
  await act(async () => finish(forecast('2026-11')));
  expect(result.current.forecast?.month).toBe('2026-12');
});
