import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import YearSummary from './YearSummary';
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
it('flags only uncovered shortfalls, including the exact zero boundary, while preserving forecast bars and month navigation', async () => {
  vi.mocked(api).mockResolvedValue([
    {
      month: '2026-01',
      income: 10000,
      expenses: 20000,
      remaining: -10000,
      deficit: true,
      savings_balance: 20000,
      remaining_with_savings: 10000,
      savings_adjusted_deficit: false,
    },
    {
      month: '2026-02',
      income: 10000,
      expenses: 30000,
      remaining: -20000,
      deficit: true,
      savings_balance: 20000,
      remaining_with_savings: 0,
      savings_adjusted_deficit: false,
    },
    {
      month: '2026-03',
      income: 10000,
      expenses: 30001,
      remaining: -20001,
      deficit: true,
      savings_balance: 20000,
      remaining_with_savings: -1,
      savings_adjusted_deficit: true,
    },
  ]);
  const selectMonth = vi.fn();
  const { container } = render(
    <YearSummary
      year="2026"
      currency="USD"
      revision={0}
      selectMonth={selectMonth}
    />,
  );
  const covered = await screen.findByRole('button', {
    name: /January 2026: income/,
  });
  expect(covered).not.toHaveClass('over');
  expect(
    screen.getByRole('button', { name: /February 2026: income/ }),
  ).not.toHaveClass('over');
  expect(
    screen.getByRole('button', { name: /March 2026: income/ }),
  ).toHaveClass('over');
  expect(container.querySelectorAll('.year-month .red')).toHaveLength(1);
  fireEvent.click(covered);
  expect(selectMonth).toHaveBeenCalledWith('2026-01');
  fireEvent.click(screen.getByText('View annual forecast table'));
  const january = screen
    .getByRole('button', { name: 'Jan 2026' })
    .closest('tr')!;
  expect(within(january).getByText('-$100.00')).toBeInTheDocument();
  expect(january.children[4]).toHaveTextContent('$100.00');
  expect(screen.getByText(/Cash carries forward/)).toBeInTheDocument();
});

it('marks an annual funding gap even when the running cash forecast stays positive', async () => {
  vi.mocked(api).mockResolvedValue([
    {
      month: '2026-12',
      income: 200000,
      expenses: 12500,
      remaining: 187500,
      deficit: false,
      savings_balance: 50000,
      remaining_with_savings: 300000,
      savings_adjusted_deficit: false,
      funding_gap: 75000,
      income_complete: true,
    },
  ]);
  render(
    <YearSummary
      year="2026"
      currency="USD"
      revision={0}
      selectMonth={vi.fn()}
    />,
  );
  const december = await screen.findByRole('button', {
    name: /December 2026:.*annual bill funding gap \$750.00/,
  });
  expect(december).toHaveClass('over');
  fireEvent.click(screen.getByText('View annual forecast table'));
  expect(screen.getByText('$750.00')).toHaveClass('red');
});
