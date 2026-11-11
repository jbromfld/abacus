import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import { useCardFreshness } from './useCardFreshness';
vi.mock('./api', () => ({ api: vi.fn() }));

it('clears a failed refresh after reconnect without replacing unrelated errors', async () => {
  vi.mocked(api).mockReset();
  vi.mocked(api)
    .mockRejectedValueOnce(new TypeError('Load failed'))
    .mockResolvedValue([]);
  const updated = vi.fn();
  const { result } = renderHook(() => useCardFreshness(updated));
  await act(() => result.current.refresh());
  expect(result.current.error).toContain('Could not refresh');
  act(() => window.dispatchEvent(new Event('online')));
  await waitFor(() => expect(result.current.error).toBe(''));
  expect(updated).toHaveBeenCalledWith([]);
});

it('does not overlap refresh requests and ignores a result after unmount', async () => {
  let finish: (cards: unknown[]) => void = () => {};
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const updated = vi.fn();
  const { result, unmount } = renderHook(() => useCardFreshness(updated));
  let pending: Promise<void>;
  act(() => {
    pending = result.current.refresh();
    void result.current.refresh();
  });
  expect(api).toHaveBeenCalledTimes(1);
  unmount();
  await act(async () => {
    finish([]);
    await pending;
  });
  expect(updated).not.toHaveBeenCalled();
});
