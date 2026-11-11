import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import BudgetAdvisor from './BudgetAdvisor';
vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  api: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/advisor/research-status')
      return { provider: 'brave', available: true, message: '' };
    if (path === '/advisor/research-preview')
      return {
        topic: 'Miami July 2027',
        queries: ['Miami July 2027 hotels'],
        missing_details: [],
        confirmation: 'preview-token',
      };
    if (path === '/advisor/chat')
      throw new Error('Synthetic reply unavailable');
    return [];
  });
});
it('keeps web off by default and requires preview consent without sending private chat to the preview', async () => {
  render(
    <BudgetAdvisor
      entry={null}
      month="2026-11"
      currency="USD"
      model="local"
      revision={0}
    />,
  );
  const web = screen.getByRole('checkbox', {
    name: 'Enable web search',
  });
  await waitFor(() => expect(web).toBeEnabled());
  expect(web).not.toBeChecked();
  fireEvent.click(web);
  fireEvent.change(screen.getByLabelText('Ask about your budget'), {
    target: { value: 'I owe 12000 on my credit card. Can I travel?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Preview and confirm',
  );
  expect(vi.mocked(api).mock.calls.some(([p]) => p === '/advisor/chat')).toBe(
    false,
  );
  fireEvent.change(screen.getByLabelText(/Public search topic/), {
    target: { value: ' Miami July 2027 ' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'Preview public searches' }),
  );
  const consent = await screen.findByRole('checkbox', {
    name: 'I approve sending these search terms to Brave.',
  });
  expect(
    vi
      .mocked(api)
      .mock.calls.find(([p]) => p === '/advisor/research-preview')?.[2],
  ).toEqual({ topic: 'Miami July 2027' });
  fireEvent.click(consent);
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await waitFor(() =>
    expect(vi.mocked(api).mock.calls.some(([p]) => p === '/advisor/chat')).toBe(
      true,
    ),
  );
  const body = vi
    .mocked(api)
    .mock.calls.find(([p]) => p === '/advisor/chat')?.[2];
  expect(body).toMatchObject({
    use_web: true,
    research_topic: 'Miami July 2027',
    research_confirmation: 'preview-token',
  });
  await screen.findByText('Synthetic reply unavailable');
  fireEvent.change(screen.getByLabelText(/Public search topic/), {
    target: { value: 'Detroit July 2027' },
  });
  expect(
    screen.queryByRole('checkbox', {
      name: 'I approve sending these search terms to Brave.',
    }),
  ).not.toBeInTheDocument();
});

it('places actual comparisons and projected impact below chat and identifies a token-limited reply', async () => {
  const fallback = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (path !== '/advisor/chat') return fallback(path, ...args);
    return {
      reply: 'A partial response',
      reply_truncated: true,
      context: {
        spending_comparison: {
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
          accounts: [
            {
              name: 'Example card',
              previous_minor: 30000,
              current_minor: 60000,
              change_minor: 30000,
            },
          ],
          categories: [],
          budget_impact: [
            {
              month: '2026-10',
              planned_income_minor: 600000,
              actual_spending_minor: 60000,
              room_after_recorded_spending_minor: 540000,
            },
          ],
        },
        savings_projection: {
          horizon_months: 12,
          start_month: '2026-11',
          savings_known: false,
          first_bill_month_remaining: null,
          income_complete: true,
        },
        planning_capacity: {
          basis: 'Synthetic projection',
          available_savings_minor: null,
          monthly_buffer_minor: null,
          buffer_shortfall_months: [],
          months: [],
        },
        monthly_forecasts: [],
        spending_history: {
          start_month: '2026-09',
          end_month: '2026-10',
          months: [
            { month: '2026-09', status: 'partial' },
            { month: '2026-10', status: 'complete' },
          ],
          categories: [
            {
              category: 'Dining',
              monthly_net_minor: [30000, 20000],
              comparisons: [],
            },
          ],
          payees: [
            {
              payee: 'Local cafe',
              category: 'Dining',
              monthly_net_minor: [30000, 20000],
              comparisons: [],
            },
          ],
          payee_limit: 20,
          additional_payees_omitted: 0,
          payee_selection: 'Selected local payees',
        },
        recent_actuals: [],
        draft_purchases: [],
      },
    };
  });
  const { container } = render(
    <BudgetAdvisor
      entry={null}
      month="2026-11"
      currency="USD"
      model="local"
      revision={0}
    />,
  );
  fireEvent.change(screen.getByLabelText('Ask about your budget'), {
    target: { value: 'What changed in spending?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  expect(
    await screen.findByText(/reached the local model’s reply limit/),
  ).toBeInTheDocument();
  const changed = screen.getByRole('heading', {
    name: 'What changed this month?',
  });
  const impact = screen.getByRole('heading', {
    name: 'Calculated budget impact',
  });
  expect(changed.closest('.advisor-main')).toBeTruthy();
  expect(impact.closest('.advisor-main')).toBeTruthy();
  const evidence = screen.getByRole('heading', { name: 'Spending evidence' });
  expect(evidence.closest('.advisor-main')).toBeTruthy();
  expect(container.querySelector('.advisor-side')).toBeNull();
  fireEvent.click(
    screen.getByText('Local transaction history used for this answer'),
  );
  const payees = screen.getByText('Selected payees (1)');
  expect(payees.closest('.table-scroll')).toBeNull();
  fireEvent.click(payees);
  expect(
    screen.getByRole('region', { name: 'Local payee spending history' }),
  ).toHaveTextContent('Local cafe');
  expect(container.querySelector('.advisor-side')).toBeNull();
  expect(
    container.querySelector('.advisor-chat')!.compareDocumentPosition(changed) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(
    screen.getByRole('table', { name: 'By bank or card account' }),
  ).toHaveTextContent('+$300.00');
  expect(
    screen.getByText(/Incomplete imports can understate spending/),
  ).toBeInTheDocument();
  expect(screen.getByText(/Forecasts are estimates/)).toBeInTheDocument();
});

it('keeps a timed-out first question visible across budget refreshes and retries without duplicating failed history', async () => {
  const props = {
    entry: null,
    month: '2026-11',
    currency: 'USD',
    model: 'local',
    revision: 0,
  };
  const { rerender } = render(<BudgetAdvisor {...props} />);
  fireEvent.change(screen.getByLabelText('Ask about your budget'), {
    target: { value: 'Can I afford another monthly bill?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await screen.findByText('Synthetic reply unavailable');
  expect(
    screen.getByText('Can I afford another monthly bill?', {
      selector: '.chat-message p',
    }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText('A little perspective before you decide.'),
  ).not.toBeInTheDocument();
  rerender(<BudgetAdvisor {...props} revision={1} />);
  expect(screen.getByLabelText('Ask about your budget')).toHaveValue(
    'Can I afford another monthly bill?',
  );
  expect(
    screen.getByText(/This question could not be completed/),
  ).toBeInTheDocument();
  const fallback = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) =>
    path === '/advisor/chat'
      ? {
          reply: 'A completed retry.',
          context: {
            monthly_forecasts: [],
            recent_actuals: [],
            draft_purchases: [],
            planning_capacity: {
              months: [],
              buffer_shortfall_months: [],
              available_savings_minor: null,
              monthly_buffer_minor: null,
            },
          },
        }
      : fallback(path, ...args),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await screen.findByText('A completed retry.');
  const request = vi
    .mocked(api)
    .mock.calls.filter(([path]) => path === '/advisor/chat')
    .at(-1);
  expect(request?.[2]).toMatchObject({ history: [] });
  expect(
    screen.queryByText(/This question could not be completed/),
  ).not.toBeInTheDocument();
});

it('uses a current plan ID and clears a deleted plan without a context dropdown', async () => {
  const fallback = vi.mocked(api).getMockImplementation()!;
  let deleted = false;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (path === '/planning/one') {
      if (deleted) throw Object.assign(new Error('Deleted'), { status: 404 });
      return {
        id: 'one',
        name: 'Fall vacation',
        amount: 240000,
        target_date: '2027-10-01',
      };
    }
    return fallback(path, ...args);
  });
  const clear = vi.fn();
  const props = {
    entry: null,
    month: '2026-11',
    currency: 'USD',
    model: 'local',
    revision: 0,
    planId: 'one',
    onClearPlan: clear,
  };
  const { rerender } = render(<BudgetAdvisor {...props} />);
  await screen.findByText('Fall vacation');
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  expect(
    screen.queryByRole('heading', { name: 'Planner context' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('heading', { name: 'Travel research' }),
  ).not.toBeInTheDocument();
  deleted = true;
  rerender(<BudgetAdvisor {...props} revision={1} />);
  await waitFor(() => expect(clear).toHaveBeenCalledOnce());
  expect(screen.queryByText('Fall vacation')).not.toBeInTheDocument();
});
