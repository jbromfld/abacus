import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import ExpenseBreakdown from './ExpenseBreakdown';
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
vi.mock('recharts', async (original) => ({
  ...(await original<typeof import('recharts')>()),
  ResponsiveContainer: () => null,
}));
const props = {
  month: '2026-11',
  actualMonth: '2026-10',
  currentActual: false,
  onCurrentActualChange: vi.fn(),
  onMonthChange: vi.fn(),
  currency: 'USD',
  revision: 0,
};
beforeEach(() => {
  vi.mocked(api).mockReset();
  props.onMonthChange.mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    const params = new URLSearchParams(path.split('?')[1]);
    return {
      start: params.get('start'),
      end: params.get('end'),
      basis: params.get('basis'),
      charges: 0,
      refunds: 0,
      net: 0,
      entry_count: 0,
      categories: [],
      entries: [],
      months: [],
    };
  });
});
it('accepts a typed month only on commit, validates boundaries, and keeps plus/minus navigation', async () => {
  render(<ExpenseBreakdown {...props} />);
  await screen.findByText('No recorded expenses in this range');
  const month = screen.getByLabelText('Breakdown month');
  const count = vi.mocked(api).mock.calls.length;
  fireEvent.change(month, { target: { value: '2028' } });
  expect(props.onMonthChange).not.toHaveBeenCalled();
  expect(vi.mocked(api).mock.calls).toHaveLength(count);
  fireEvent.change(month, { target: { value: '2028-02' } });
  fireEvent.keyDown(month, { key: 'Enter' });
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.some(([path]) =>
          path.includes('start=2028-02-01&end=2028-02-29'),
        ),
    ).toBe(true),
  );
  expect(props.onMonthChange).toHaveBeenLastCalledWith('2028-02', 'actual');
  fireEvent.change(month, { target: { value: '2028-13' } });
  fireEvent.blur(month);
  expect(screen.getByRole('alert')).toHaveTextContent(
    '1900-01 through 9998-12',
  );
  expect(props.onMonthChange).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(month, { key: 'Escape' });
  expect(month).toHaveValue('2028-02');
  fireEvent.click(
    screen.getByRole('button', { name: 'Previous breakdown month' }),
  );
  expect(props.onMonthChange).toHaveBeenLastCalledWith('2028-01', 'actual');
  fireEvent.change(month, { target: { value: '1900-01' } });
  fireEvent.blur(month);
  expect(
    screen.getByRole('button', { name: 'Previous breakdown month' }),
  ).toBeDisabled();
});
it('separates category charts from the entries pane while retaining the chosen category and range', async () => {
  const data = {
    start: '2026-10-01',
    end: '2026-10-31',
    basis: 'actual',
    charges: 1000,
    refunds: 0,
    net: 1000,
    entry_count: 1,
    categories: [
      {
        category_id: 'food',
        name: 'Dining',
        charges: 1000,
        refunds: 0,
        net: 1000,
        entry_count: 1,
      },
    ],
    entries: [
      {
        id: 'one',
        record_id: 'one',
        date: '2026-10-03',
        month: '2026-10',
        description: 'Synthetic meal',
        category_id: 'food',
        category_name: 'Dining',
        kind: 'purchase',
        amount: 1000,
        signed_amount: 1000,
        account_name: 'Synthetic card',
      },
    ],
    months: [],
  };
  vi.mocked(api).mockResolvedValue(data);
  const show = vi.fn();
  const showBreakdown = vi.fn();
  const { rerender } = render(
    <ExpenseBreakdown {...props} onShowEntries={show} />,
  );
  const category = await screen.findByRole('button', {
    name: /Dining 1 transactions/,
  });
  expect(screen.queryByText('Synthetic meal')).not.toBeInTheDocument();
  fireEvent.click(category);
  expect(show).toHaveBeenCalledOnce();
  rerender(
    <ExpenseBreakdown
      {...props}
      view="entries"
      onShowEntries={show}
      onShowBreakdown={showBreakdown}
    />,
  );
  expect(await screen.findByText('Synthetic meal')).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /Dining 1 transactions/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText('Breakdown month')).toHaveValue('2026-10');
  fireEvent.click(screen.getByRole('button', { name: 'All categories' }));
  expect(showBreakdown).toHaveBeenCalledOnce();
  rerender(<ExpenseBreakdown {...props} view="breakdown" />);
  expect(
    screen.getByRole('heading', { name: 'Expense breakdown' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: /Dining 1 transactions/ }),
  ).toBeInTheDocument();
});
