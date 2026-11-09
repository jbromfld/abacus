import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import { useAlertDismissals } from './useAlertDismissals';
vi.mock('./api', () => ({ api: vi.fn() }));
beforeEach(() => {
  vi.mocked(api).mockReset();
});
it('restores persisted month-specific acknowledgements after a remount without suppressing other alerts', async () => {
  let records: { month: string; kind: string; dismissed_at: string }[] = [];
  vi.mocked(api).mockImplementation(async (_path, method, body) => {
    if (method === 'POST') {
      const record = {
        ...(body as { month: string; kind: string }),
        dismissed_at: '2026-11-09T12:00:00Z',
      };
      records.push(record);
      return record;
    }
    if (method === 'DELETE') {
      records = [];
      return { restored: 1 };
    }
    return [...records];
  });
  const first = renderHook(() => useAlertDismissals());
  await waitFor(() => expect(first.result.current.ready).toBe(true));
  await act(async () =>
    first.result.current.dismiss('actual_deficit', '2026-09'),
  );
  expect(first.result.current.isDismissed('actual_deficit', '2026-09')).toBe(
    true,
  );
  expect(first.result.current.isDismissed('actual_deficit', '2026-10')).toBe(
    false,
  );
  expect(first.result.current.isDismissed('forecast_deficit', '2026-09')).toBe(
    false,
  );
  first.unmount();
  const next = renderHook(() => useAlertDismissals());
  await waitFor(() => expect(next.result.current.ready).toBe(true));
  expect(next.result.current.isDismissed('actual_deficit', '2026-09')).toBe(
    true,
  );
  await act(async () => next.result.current.restore());
  expect(next.result.current.isDismissed('actual_deficit', '2026-09')).toBe(
    false,
  );
});
it('keeps alerts visible when loading or saving acknowledgements fails', async () => {
  vi.mocked(api).mockRejectedValue(new Error('Unavailable'));
  const { result } = renderHook(() => useAlertDismissals());
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current.error).toContain('Could not load');
  await act(async () => result.current.dismiss('actual_deficit', '2026-09'));
  expect(result.current.isDismissed('actual_deficit', '2026-09')).toBe(false);
  expect(result.current.error).toContain('remains visible');
});
