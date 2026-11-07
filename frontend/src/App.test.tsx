import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import App from './App';
vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  api: vi.fn(),
  monthNow: () => '2026-11',
}));
vi.mock('./UpcomingBills', () => ({ default: () => null }));
vi.mock('./ReserveMonitor', () => ({ default: () => null }));
it('never displays November totals under December after its request fails, and skips hidden trend reads', async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/settings')
      return {
        currency: 'USD',
        model: '',
        advisor_enabled: false,
        reserve_alerts_enabled: false,
        reserve_checkpoint_day: 1,
      };
    if (path === '/categories') return [{ id: 'other', name: 'Other' }];
    if (path === '/forecast?month=2026-12')
      throw new Error('Synthetic December failure');
    if (path.startsWith('/forecast?'))
      return {
        month: new URLSearchParams(path.split('?')[1]).get('month'),
        income: 100000,
        expenses: 105000,
        remaining: -5000,
        deficit: true,
        lines: [],
        actual: {
          expenses: 0,
          status: 'missing',
          marked_complete: false,
          transaction_count: 0,
        },
        actual_deficit: false,
      };
    return [];
  });
  render(<App />);
  expect(await screen.findByText('$1,050.00')).toBeInTheDocument();
  await waitFor(() =>
    expect(vi.mocked(api).mock.calls.some(([p]) => p === '/settings')).toBe(
      true,
    ),
  );
  expect(vi.mocked(api).mock.calls.some(([p]) => p.startsWith('/trends'))).toBe(
    false,
  );
  fireEvent.change(screen.getByLabelText('Selected month', { exact: true }), {
    target: { value: '2026-12' },
  });
  expect(
    await screen.findByText('Synthetic December failure'),
  ).toBeInTheDocument();
  expect(screen.queryByText('$1,050.00')).not.toBeInTheDocument();
  expect(
    screen.queryByText(/Forecast expenses exceed income/),
  ).not.toBeInTheDocument();
});
