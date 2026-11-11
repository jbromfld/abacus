import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import AnnualExpectedIncome from './AnnualExpectedIncome';

vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(api).mockReset();
});
const summary = {
  year: 2026,
  total: 120000,
  included_total: 0,
  monthly_amounts: Array(12).fill(0),
  sources: [
    {
      id: 'refund',
      year: 2026,
      name: 'Tax refund',
      amount: 120000,
      included: false,
      monthly_amounts: Array(12).fill(10000),
    },
  ],
};

it('edits a yearly source with its slider, opts into monthly income explicitly, and saves once', async () => {
  vi.mocked(api).mockResolvedValue(summary);
  const changed = vi.fn();
  render(
    <AnnualExpectedIncome
      year={2026}
      currency="USD"
      revision={0}
      onChanged={changed}
    />,
  );
  const form = await screen.findByRole('form', { name: 'Edit Tax refund' });
  const toggle = within(form).getByRole('checkbox');
  expect(toggle).not.toBeChecked();
  fireEvent.change(within(form).getByRole('slider'), {
    target: { value: '240000' },
  });
  expect(within(form).getByLabelText('Tax refund annual amount')).toHaveValue(
    2400,
  );
  expect(
    vi.mocked(api).mock.calls.filter(([, method]) => method === 'PUT'),
  ).toHaveLength(0);
  fireEvent.click(toggle);
  fireEvent.click(within(form).getByRole('button', { name: 'Save estimate' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith('/annual-income/refund', 'PUT', {
      year: 2026,
      name: 'Tax refund',
      amount: 240000,
      included: true,
    }),
  );
  expect(changed).toHaveBeenCalledOnce();
});

it('keeps failed source additions editable and never shows the previous year under a new year', async () => {
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (method === 'POST') throw new Error('Synthetic save failure');
    if (path.includes('2027')) throw new Error('Synthetic year unavailable');
    return summary;
  });
  const props = {
    year: 2026,
    currency: 'JPY',
    revision: 0,
    onChanged: vi.fn(),
  };
  const { rerender } = render(<AnnualExpectedIncome {...props} />);
  const form = await screen.findByRole('form', {
    name: 'Add annual income source',
  });
  fireEvent.change(within(form).getByLabelText('New income source name'), {
    target: { value: 'Sale proceeds' },
  });
  fireEvent.change(
    within(form).getByLabelText('New income source annual amount'),
    { target: { value: '12001' } },
  );
  fireEvent.click(
    within(form).getByRole('button', { name: 'Add income source' }),
  );
  await screen.findByText('Synthetic save failure');
  expect(within(form).getByLabelText('New income source name')).toHaveValue(
    'Sale proceeds',
  );
  expect(api).toHaveBeenCalledWith('/annual-income', 'POST', {
    year: 2026,
    name: 'Sale proceeds',
    amount: 12001,
    included: false,
  });
  expect(props.onChanged).not.toHaveBeenCalled();
  rerender(<AnnualExpectedIncome {...props} year={2027} />);
  await screen.findByText('Synthetic year unavailable');
  expect(
    screen.queryByRole('form', { name: 'Edit Tax refund' }),
  ).not.toBeInTheDocument();
});
