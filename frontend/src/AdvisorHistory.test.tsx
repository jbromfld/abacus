import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import AdvisorHistory from './AdvisorHistory';
import type { AdvisorSpendingHistory } from './api';

it('shows the local evidence, exact changes, and incomplete or missing data without treating missing as zero', () => {
  const history: AdvisorSpendingHistory = {
    start_month: '2026-08',
    end_month: '2026-10',
    months: [
      { month: '2026-08', status: 'missing' },
      { month: '2026-09', status: 'partial' },
      { month: '2026-10', status: 'complete' },
    ],
    basis: 'Net spending',
    categories: [
      {
        category: 'Dining',
        monthly_net_minor: [null, 15000, 20000],
        comparisons: [
          {
            months: 2,
            from_month: '2026-09',
            to_month: '2026-10',
            first_month_minor: 15000,
            last_month_minor: 20000,
            change_minor: 5000,
            partial_month_count: 1,
            missing_month_count: 0,
          },
          {
            months: 3,
            from_month: '2026-08',
            to_month: '2026-10',
            first_month_minor: null,
            last_month_minor: 20000,
            change_minor: null,
            partial_month_count: 1,
            missing_month_count: 1,
          },
        ],
      },
    ],
    payees: [],
    payee_limit: 20,
    additional_payees_omitted: 3,
    payee_selection: 'Largest recorded increases',
  };
  render(<AdvisorHistory history={history} currency="USD" />);
  // Details are deliberately closed initially; the recorded snapshot stays inspectable.
  const table = screen.getByRole('table', { hidden: true, name: /Categories/ });
  expect(within(table).getByText('$50.00')).toBeInTheDocument();
  expect(within(table).getByText('Missing')).toBeInTheDocument();
  expect(within(table).getByText('Unknown')).toBeInTheDocument();
  expect(
    within(table).getByText(/2026-09 → 2026-10 · incomplete data/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/never included in Brave search requests/),
  ).toBeInTheDocument();
});
