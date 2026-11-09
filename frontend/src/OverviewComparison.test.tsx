import { render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import OverviewComparison from './OverviewComparison';
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
it('loads the previous finished months without an advisor and refreshes after transaction changes', async () => {
  const comparison = {
    previous_month: '2026-09',
    month: '2026-10',
    previous_status: 'partial',
    current_status: 'complete',
    totals: {
      name: 'All recorded spending',
      previous_minor: 30000,
      current_minor: 60000,
      change_minor: 30000,
    },
    accounts: [],
    categories: [],
  };
  vi.mocked(api).mockResolvedValue({ comparison });
  const { rerender } = render(
    <OverviewComparison currency="USD" revision={0} />,
  );
  expect(
    await screen.findByRole('table', { name: 'By bank or card account' }),
  ).toHaveTextContent('+$300.00');
  expect(screen.getByText(/recorded transactions/)).toHaveTextContent(
    'Sep 2026 → Oct 2026',
  );
  rerender(<OverviewComparison currency="USD" revision={1} />);
  await waitFor(() => expect(vi.mocked(api)).toHaveBeenCalledTimes(2));
  expect(
    vi
      .mocked(api)
      .mock.calls.every(([path]) => path === '/spending/comparison'),
  ).toBe(true);
});
