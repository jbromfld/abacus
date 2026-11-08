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
    return [];
  });
  render(<App />);
  fireEvent.click(
    await screen.findByRole('button', { name: 'Budget advisor', exact: true }),
  );
  const question = await screen.findByLabelText('Ask about your budget');
  fireEvent.change(question, { target: { value: 'How could I save more?' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask', exact: true }));
  await screen.findByText('Your original savings discussion.');
  fireEvent.change(question, { target: { value: 'My unfinished follow-up' } });
  fireEvent.click(
    screen.getByRole('button', { name: 'Settings', exact: true }),
  );
  await screen.findByRole('heading', { name: 'Advisor memory', exact: true });
  fireEvent.click(
    screen.getByRole('button', { name: 'Budget advisor', exact: true }),
  );
  expect(
    screen.getByText('Your original savings discussion.'),
  ).toBeInTheDocument();
  expect(screen.getByLabelText('Ask about your budget')).toHaveValue(
    'My unfinished follow-up',
  );

  fireEvent.click(
    screen.getByRole('button', { name: 'Recurring accounts', exact: true }),
  );
  fireEvent.click(
    await screen.findByRole('button', { name: 'Add account', exact: true }),
  );
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
  fireEvent.click(
    within(dialog).getByRole('button', { name: 'Save', exact: true }),
  );
  await screen.findByText('Updating budget…');
  fireEvent.click(
    screen.getByRole('button', { name: 'Budget advisor', exact: true }),
  );
  expect(screen.getByLabelText('Ask about your budget')).toBe(question);
  expect(question).toHaveValue('My unfinished follow-up');
  expect(
    screen.getByText('Your original savings discussion.'),
  ).toBeInTheDocument();
  await act(async () => finishRefresh(forecast));
  expect(screen.getByLabelText('Ask about your budget')).toBe(question);
  fireEvent.click(screen.getByRole('button', { name: 'Ask', exact: true }));
  await waitFor(() => expect(requestCount).toBe(2));
  fireEvent.click(
    screen.getByRole('button', { name: 'Recurring accounts', exact: true }),
  );
  await act(async () =>
    finishAnswer({ reply: 'Your preserved follow-up answer.', context }),
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'Budget advisor', exact: true }),
  );
  expect(
    screen.getByText('Your preserved follow-up answer.'),
  ).toBeInTheDocument();
  expect(
    screen.getByText('Your original savings discussion.'),
  ).toBeInTheDocument();
});
