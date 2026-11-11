import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import App from './App';
vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  api: vi.fn(),
  monthNow: () => '2026-11',
}));
vi.mock('./UpcomingBills', () => ({ default: () => null }));
vi.mock('./ReserveMonitor', () => ({
  default: ({ collapsible }: { collapsible?: boolean }) =>
    collapsible ? <section aria-label="Overview reserve" /> : null,
}));
vi.mock('./ExpenseBreakdown', () => ({ default: () => null }));
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
    if (path === '/payee-review/payees')
      return { total: 0, groups: [], ungrouped: [], review: null };
    if (path === '/planning/categories') return [];
    if (path.startsWith('/planning'))
      return { plans: [], total_planned: 0, set_aside: null };
    return [];
  });
  render(<App />);
  expect(await screen.findByText('$1,050.00')).toBeInTheDocument();
  const stats = screen
    .getByText('Planned expenses')
    .closest('.overview-stats')!;
  expect(stats.children).toHaveLength(3);
  expect(screen.getByRole('button', { name: 'Planning' })).toBeInTheDocument();
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
  fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
  expect(screen.getByLabelText('Selected month', { exact: true })).toHaveValue(
    '2026-11',
  );
  expect(await screen.findByText('$1,050.00')).toBeInTheDocument();
  expect(
    screen.queryByText('Synthetic December failure'),
  ).not.toBeInTheDocument();
  const previousReads = vi
    .mocked(api)
    .mock.calls.filter(([path]) => path === '/forecast?month=2026-11').length;
  fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.filter(([path]) => path === '/forecast?month=2026-11')
        .length,
    ).toBeGreaterThan(previousReads),
  );
});

it('keeps advisor messages, drafts and in-flight replies mounted while saving a recurring bill refreshes the workspace', async () => {
  vi.mocked(api).mockReset();
  let refreshing = false;
  let finishRefresh: (value: unknown) => void = () => {};
  const forecast = {
    month: '2026-11',
    income: 600000,
    expenses: 15000,
    remaining: 585000,
    deficit: false,
    lines: [],
    actual: {
      expenses: 0,
      status: 'missing',
      marked_complete: false,
      transaction_count: 0,
    },
    actual_deficit: false,
  };
  const context = {
    monthly_forecasts: [],
    recent_actuals: [],
    draft_purchases: [],
    planning_capacity: {
      months: [],
      buffer_shortfall_months: [],
      available_savings_minor: null,
      monthly_buffer_minor: null,
    },
  };
  let finishAnswer: (value: unknown) => void = () => {};
  let requestCount = 0;
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (path === '/settings')
      return {
        currency: 'USD',
        model: 'local',
        advisor_enabled: true,
        advisor_memory_enabled: false,
        reserve_alerts_enabled: false,
        reserve_checkpoint_day: 1,
      };
    if (path === '/categories') return [{ id: 'other', name: 'Other' }];
    if (path === '/models') return { models: ['local'], error: '' };
    if (path === '/savings')
      return { amount: null, month: '2026-11', floor: 0 };
    if (path === '/advisor/research-status')
      return { available: false, provider: 'brave', message: '' };
    if (path === '/advisor/chat') {
      requestCount++;
      if (requestCount === 1)
        return { reply: 'Your original savings discussion.', context };
      return new Promise((resolve) => {
        finishAnswer = resolve;
      });
    }
    if (path === '/recurring' && method === 'POST') {
      refreshing = true;
      return {};
    }
    if (path === '/forecast?month=2026-11' && refreshing)
      return new Promise((resolve) => {
        finishRefresh = resolve;
      });
    if (path.startsWith('/forecast?'))
      return { ...forecast, month: path.split('=')[1] };
    if (path === '/payee-review/payees')
      return { total: 0, groups: [], ungrouped: [], review: null };
    if (path === '/planning/categories') return [];
    if (path.startsWith('/planning'))
      return { plans: [], total_planned: 0, set_aside: null };
    return [];
  });
  render(<App />);
  fireEvent.click(
    await screen.findByRole('button', { name: 'Budget advisor' }),
  );
  const question = await screen.findByLabelText('Ask about your budget');
  fireEvent.change(question, { target: { value: 'How could I save more?' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await screen.findByText('Your original savings discussion.');
  fireEvent.change(question, { target: { value: 'My unfinished follow-up' } });
  fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
  await screen.findByRole('heading', { name: 'Advisor memory' });
  fireEvent.click(screen.getByRole('button', { name: 'Budget advisor' }));
  expect(
    screen.getByText('Your original savings discussion.'),
  ).toBeInTheDocument();
  expect(screen.getByLabelText('Ask about your budget')).toHaveValue(
    'My unfinished follow-up',
  );

  fireEvent.click(screen.getByRole('button', { name: 'Recurring accounts' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Add account' }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Name', { exact: true }), {
    target: { value: 'New bill' },
  });
  fireEvent.change(within(dialog).getByLabelText(/^Amount \(USD\)/), {
    target: { value: '200' },
  });
  fireEvent.change(
    within(dialog).getByLabelText(/^Category \(required for payables\)/),
    { target: { value: 'other' } },
  );
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
  await screen.findByText('Updating budget…');
  fireEvent.click(screen.getByRole('button', { name: 'Budget advisor' }));
  expect(screen.getByLabelText('Ask about your budget')).toBe(question);
  expect(question).toHaveValue('My unfinished follow-up');
  expect(
    screen.getByText('Your original savings discussion.'),
  ).toBeInTheDocument();
  await act(async () => finishRefresh(forecast));
  expect(screen.getByLabelText('Ask about your budget')).toBe(question);
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await waitFor(() => expect(requestCount).toBe(2));
  fireEvent.click(screen.getByRole('button', { name: 'Recurring accounts' }));
  await act(async () =>
    finishAnswer({ reply: 'Your preserved follow-up answer.', context }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Budget advisor' }));
  expect(
    screen.getByText('Your preserved follow-up answer.'),
  ).toBeInTheDocument();
  expect(
    screen.getByText('Your original savings discussion.'),
  ).toBeInTheDocument();
});

it('keeps transactions mounted through minute timers and manual refreshes while hiding rows from another month', async () => {
  vi.mocked(api).mockReset();
  const timers = vi.spyOn(globalThis, 'setInterval');
  const account = {
    id: 'bank',
    name: 'Synthetic bank',
    stale_alert_enabled: false,
    stale: false,
  };
  const transaction = {
    id: 'stable-row',
    description: 'Transaction anchor',
    date: '2026-10-02',
    amount: 1000,
    kind: 'purchase',
    category_id: 'other',
    account_id: 'bank',
  };
  const report = (month: string) => ({
    month,
    income: 100000,
    expenses: 1000,
    remaining: 99000,
    deficit: false,
    lines: [],
    actual: {
      expenses: 1000,
      status: 'partial',
      marked_complete: false,
      transaction_count: 1,
    },
    actual_deficit: false,
  });
  let hold = false;
  const pending: (() => void)[] = [];
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/settings')
      return {
        currency: 'USD',
        model: '',
        advisor_enabled: false,
        advisor_memory_enabled: false,
        reserve_alerts_enabled: false,
        reserve_checkpoint_day: 1,
      };
    if (path === '/categories') return [{ id: 'other', name: 'Other' }];
    if (path === '/accounts') return [account];
    if (path === '/recurring')
      return [{ id: 'ach', name: 'ACH bill', ach_enabled: true }];
    if (path.startsWith('/forecast?')) {
      const value = report(path.split('=')[1]);
      if (hold)
        return new Promise((resolve) => pending.push(() => resolve(value)));
      return value;
    }
    if (path.startsWith('/transactions?')) {
      if (hold)
        return new Promise((resolve) =>
          pending.push(() => resolve([{ ...transaction, amount: 1500 }])),
        );
      return [transaction];
    }
    if (path === '/payee-review/payees')
      return { total: 0, groups: [], ungrouped: [], review: null };
    if (path === '/planning/categories') return [];
    if (path.startsWith('/planning'))
      return { plans: [], total_planned: 0, set_aside: null };
    return [];
  });
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Spending' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Transactions' }));
  const anchor = await screen.findByText('Transaction anchor');
  const row = anchor.closest('tr')!;
  fireEvent.change(screen.getByLabelText('Search transactions'), {
    target: { value: 'anchor' },
  });
  vi.mocked(api).mockClear();
  hold = true;
  await act(async () => {
    for (const [callback, delay] of timers.mock.calls) {
      if (delay === 60000 && typeof callback === 'function') callback();
    }
  });
  expect(
    vi
      .mocked(api)
      .mock.calls.some(
        ([path]) =>
          path.startsWith('/transactions?') || path.startsWith('/forecast?'),
      ),
  ).toBe(false);
  expect(screen.getByText('Transaction anchor').closest('tr')).toBe(row);
  fireEvent.click(
    screen.getByRole('button', { name: 'Refresh spending data' }),
  );
  await waitFor(() => expect(pending.length).toBeGreaterThanOrEqual(3));
  expect(screen.getByText('Transaction anchor').closest('tr')).toBe(row);
  expect(screen.queryByText('Loading transactions…')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Search transactions')).toHaveValue('anchor');
  await act(async () => {
    pending.splice(0).forEach((resolve) => resolve());
  });
  expect(screen.getByText('Transaction anchor').closest('tr')).toBe(row);
  expect(within(row).getByText('$15.00')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Selected month', { exact: true }), {
    target: { value: '2026-12' },
  });
  expect(screen.queryByText('Transaction anchor')).not.toBeInTheDocument();
});
