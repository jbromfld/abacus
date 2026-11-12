import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import Planning from './Planning';
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
const data = {
  savings: 800000,
  savings_month: '2026-11',
  floor: 0,
  total_planned: 0,
  set_aside: 0,
  free_savings: 800000,
  basis: 'Shared savings',
  plans: [],
  projection: null,
  categories: [
    { id: 'tax', name: 'tax' },
    { id: 'vacation', name: 'vacation' },
    { id: 'purchase', name: 'purchase' },
  ],
  annual_expenses: [
    {
      id: 'winter',
      name: 'Winter tax',
      amount: 300000,
      target_date: '2027-02-15',
    },
  ],
};
const props = {
  currency: 'USD',
  revision: 0,
  onChanged: vi.fn(),
  onDiscuss: vi.fn(),
  onDeleted: vi.fn(),
  onDraftUsed: vi.fn(),
};
beforeEach(() => {
  vi.mocked(api).mockReset();
  Object.values(props).forEach((value) => {
    if (typeof value === 'function') value.mockClear();
  });
  vi.mocked(api).mockImplementation(async (path) =>
    path === '/savings' ? { amount: 800000, month: '2026-11', floor: 0 } : data,
  );
});
it('creates a plan with three required values and a slider, without adding budget or transaction fields', async () => {
  render(<Planning {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Add a plan' }));
  const form = within(screen.getByRole('dialog'));
  fireEvent.change(form.getByLabelText('Plan name'), {
    target: { value: 'Fall vacation' },
  });
  fireEvent.change(form.getByRole('slider', { name: 'Target amount slider' }), {
    target: { value: '240000' },
  });
  expect(form.getByLabelText('Target amount')).toHaveValue(2400);
  fireEvent.change(form.getByLabelText('Target date'), {
    target: { value: '2027-10-01' },
  });
  fireEvent.change(form.getByLabelText('Planning category'), {
    target: { value: 'vacation' },
  });
  expect(
    form.queryByText(/baseline|checkpoint|monthly buffer/i),
  ).not.toBeInTheDocument();
  fireEvent.click(form.getByRole('button', { name: 'Save plan' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      '/planning',
      'POST',
      expect.objectContaining({
        name: 'Fall vacation',
        amount: 240000,
        target_date: '2027-10-01',
        category_id: 'vacation',
        recurring_id: null,
        request_id: expect.any(String),
      }),
    ),
  );
  expect(props.onChanged).toHaveBeenCalledOnce();
});
it('prefills a linked annual expense in the same short form', async () => {
  render(<Planning {...props} />);
  fireEvent.click(
    await screen.findByRole('button', { name: 'Use annual expense' }),
  );
  const form = within(screen.getByRole('dialog'));
  fireEvent.change(form.getByLabelText('Use an annual expense'), {
    target: { value: 'winter' },
  });
  expect(form.getByLabelText('Plan name')).toHaveValue('Winter tax');
  expect(form.getByLabelText('Target amount')).toHaveValue(3000);
  expect(form.getByLabelText('Target date')).toHaveValue('2027-02-15');
  fireEvent.click(form.getByRole('button', { name: 'Save plan' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      '/planning',
      'POST',
      expect.objectContaining({ recurring_id: 'winter', category_id: 'tax' }),
    ),
  );
});
it('reviews advisor suggestions before saving and keeps failed edits available', async () => {
  const draft = {
    key: 1,
    value: {
      name: 'Vacation',
      amount: 120000,
      target_date: '2027-10-01',
      category_id: 'vacation',
    },
  };
  const fallback = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (args[0] === 'POST') throw new Error('Synthetic save failure');
    return fallback(path, ...args);
  });
  render(<Planning {...props} initialDraft={draft} />);
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByLabelText('Plan name')).toHaveValue('Vacation');
  expect(
    vi.mocked(api).mock.calls.some(([, method]) => method === 'POST'),
  ).toBe(false);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save plan' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Synthetic save failure',
  );
  expect(within(dialog).getByLabelText('Target amount')).toHaveValue(1200);
  expect(props.onChanged).not.toHaveBeenCalled();
});

it('links an existing goal and keeps bill-owned values read-only', async () => {
  const goal = {
    id: 'goal',
    name: 'Taxes',
    amount: 150000,
    target_date: '2026-12-31',
    category_id: 'tax',
    recurring_id: null,
  };
  render(<Planning {...props} initialDraft={{ key: 3, value: goal }} />);
  const dialog = await screen.findByRole('dialog');
  const form = within(dialog);
  fireEvent.change(form.getByLabelText('Use an annual expense'), {
    target: { value: 'winter' },
  });
  expect(form.getByLabelText('Target amount')).toBeDisabled();
  expect(form.getByLabelText('Target date')).toBeDisabled();
  fireEvent.click(form.getByRole('button', { name: 'Save plan' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      '/planning/goal',
      'PUT',
      expect.objectContaining({ recurring_id: 'winter', amount: 300000 }),
    ),
  );
});

it('shows annual funding separately from positive projected cash in December Overview', async () => {
  const { PlanningOverview } = await import('./Planning');
  const row = {
    id: 'winter-plan',
    name: 'Winter tax',
    amount: 150000,
    target_date: '2026-12-31',
    category_id: 'tax',
    category: 'tax',
    recurring_id: 'winter',
    recurring_name: 'Winter tax',
    set_aside: 50000,
    still_needed: 100000,
    monthly_needed: 37500,
    contribution_count: 2,
    status: 'saving',
    monthly_allocation: 12500,
    projected_contributions: 25000,
    projected_funding: 75000,
    funding_gap: 75000,
  };
  vi.mocked(api).mockImplementation(async (path) =>
    path.startsWith('/planning')
      ? {
          ...data,
          plans: [row],
          total_planned: 150000,
          set_aside: 50000,
          projection: {
            income_complete: true,
            basis: '',
            months: [
              { month: '2026-12', balance: 300000, plan_payments: 150000 },
            ],
          },
        }
      : { amount: 50000, month: '2026-11', floor: 0 },
  );
  const onOpen = vi.fn();
  render(
    <PlanningOverview
      currency="USD"
      revision={0}
      month="2026-12"
      onOpen={onOpen}
      onChanged={props.onChanged}
    />,
  );
  const warning = await screen.findByText(/\$750.00 additional funding needed/);
  expect(warning.closest('details')).not.toHaveAttribute('open');
  expect(
    screen.getByText(/Projected end-of-month cash: \$3,000.00/),
  ).toBeInTheDocument();
  expect(screen.getByText('Projected contributions')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Open Planning' }));
  expect(onOpen).toHaveBeenCalledOnce();
});
