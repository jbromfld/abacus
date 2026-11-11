import { afterEach, expect, it, vi } from 'vitest';
import { api } from './api';
afterEach(() => vi.unstubAllGlobals());

it('explains interrupted transport failures without resending advisor messages', async () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError('Load failed'));
  vi.stubGlobal('fetch', fetcher);
  await expect(
    api('/advisor/chat', 'POST', { message: 'test' }),
  ).rejects.toMatchObject({
    status: 0,
    message: expect.stringContaining('Connection to Abacus was interrupted'),
  });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it('keeps cancellation separate from connection failures', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockRejectedValue(new DOMException('Cancelled', 'AbortError')),
  );
  const controller = new AbortController();
  controller.abort();
  await expect(
    api('/advisor/chat', 'POST', {}, controller.signal),
  ).rejects.toMatchObject({ name: 'AbortError' });
});

it('explains a connection interrupted while reading the advisor reply', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: () => Promise.reject(new TypeError('Load failed')),
      }),
  );
  await expect(
    api('/advisor/chat', 'POST', { message: 'test' }),
  ).rejects.toMatchObject({
    status: 0,
    message: expect.stringContaining('Connection to Abacus was interrupted'),
  });
});
