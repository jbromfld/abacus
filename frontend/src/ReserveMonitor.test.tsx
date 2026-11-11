import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import type { ReserveCheck } from './api';
import ReserveMonitor from './ReserveMonitor';

vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
const report: ReserveCheck = {
  today: '2026-11-11',
  enabled: true,
  checkpoint_day: 1,
  eligible_bill_count: 1,
  status: 'below_target',
  dismissed: false,
  plan: {
    amount: 50000,
    start_date: '2026-11-01',
    schedules: [],
    schedule_changed: false,
    dismissed_until: null,
  },
  observations: [{ amount: 40000, as_of: '2026-11-11' }],
  target: 50000,
  target_as_of: '2026-11-11',
  next_checkpoint: '2026-12-01',
  next_target: 60000,
  latest: { amount: 40000, as_of: '2026-11-11' },
  shortfall: 10000,
  fresh: true,
  checkpoints: [],
  upcoming: [],
};
const deleted: ReserveCheck = {
  ...report,
  status: 'not_configured',
  plan: null,
};
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (path === '/savings')
      return { amount: 40000, month: '2026-11', floor: 0 };
    return method === 'DELETE' ? deleted : report;
  });
});

it('collapses overview details while keeping the warning visible and respects the chosen state on refresh', async () => {
  const props = {
    currency: 'USD',
    revision: 0,
    collapsible: true,
    onConfigure: vi.fn(),
    onChanged: vi.fn(),
  };
  const { rerender } = render(<ReserveMonitor {...props} />);
  const toggle = await screen.findByRole('button', {
    name: 'Show reserve details',
  });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(screen.getByRole('alert')).toHaveTextContent(
    'below your planned annual-bill reserve',
  );
  expect(
    screen.queryByRole('button', { name: 'Update savings' }),
  ).not.toBeInTheDocument();
  fireEvent.click(toggle);
  expect(screen.getByRole('button', { name: 'Update savings' })).toBeVisible();
  rerender(<ReserveMonitor {...props} revision={1} />);
  expect(
    screen.getByRole('button', { name: 'Hide reserve details' }),
  ).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(screen.getByRole('button', { name: 'Hide reserve details' }));
  expect(
    screen.queryByRole('button', { name: 'Update savings' }),
  ).not.toBeInTheDocument();
});

it('requires confirmation, permanently deletes the plan and returns to setup', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const changed = vi.fn();
  render(
    <ReserveMonitor
      manage
      currency="USD"
      revision={0}
      onConfigure={() => {}}
      onChanged={changed}
    />,
  );
  const remove = await screen.findByRole('button', {
    name: 'Permanently delete reserve plan',
  });
  fireEvent.click(remove);
  expect(
    vi.mocked(api).mock.calls.some(([, method]) => method === 'DELETE'),
  ).toBe(false);
  confirm.mockReturnValue(true);
  fireEvent.click(remove);
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith('/reserve-check/plan', 'DELETE'),
  );
  expect(await screen.findByText('Set funding target')).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Permanently delete reserve plan' }),
  ).not.toBeInTheDocument();
  expect(changed).toHaveBeenCalledOnce();
});

it('retains the plan and reports a failed deletion without claiming success', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const fallback = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (args[0] === 'DELETE') throw new Error('Synthetic deletion failure');
    return fallback(path, ...args);
  });
  const changed = vi.fn();
  render(
    <ReserveMonitor
      manage
      currency="USD"
      revision={0}
      onConfigure={() => {}}
      onChanged={changed}
    />,
  );
  fireEvent.click(
    await screen.findByRole('button', {
      name: 'Permanently delete reserve plan',
    }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Synthetic deletion failure',
  );
  expect(
    screen.getByRole('button', { name: 'Permanently delete reserve plan' }),
  ).toBeEnabled();
  expect(changed).not.toHaveBeenCalled();
});
