import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import type { ImportJob } from './api';
import ImportReview from './ImportReview';
vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  api: vi.fn(),
}));
it('asks before replacing reviewed PDF rows and preserves edits on a failed request', async () => {
  const job: ImportJob = {
    id: 'pdf',
    filename: 'synthetic.pdf',
    period: '2026-11',
    status: 'failed',
    account_id: 'card',
    error: '',
    source: { type: 'pdf', headers: [], preview: [] },
    rows: [
      {
        date: '2026-11-01',
        description: 'Corrected store',
        amount: 1234,
        kind: 'purchase',
        category_id: 'food',
        selected: true,
        errors: [],
      },
    ],
  };
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith('/review')) return job;
    throw new Error('Model unavailable');
  });
  render(
    <ImportReview
      initial={job}
      categories={[{ id: 'food', name: 'Food' }]}
      currency="USD"
      onClose={() => {}}
      onChanged={() => {}}
    />,
  );
  const retry = screen.getByRole('button', {
    name: 'Extract PDF transactions / retry',
  });
  fireEvent.click(retry);
  expect(confirm).toHaveBeenCalled();
  expect(api).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  fireEvent.click(retry);
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent('Model unavailable'),
  );
  expect(screen.getByLabelText('Description row 1')).toHaveValue(
    'Corrected store',
  );
  expect(
    vi.mocked(api).mock.calls.find(([p]) => p.endsWith('/process'))?.[2],
  ).toEqual({ replace_review: true });
});

it('preserves edits across pages and saves all review rows', async () => {
  const rows = Array.from({ length: 201 }, (_, i) => ({
    date: '2026-11-01',
    description: `Store ${i + 1}`,
    amount: 100,
    kind: 'purchase',
    category_id: 'food',
    selected: true,
    errors: [],
  }));
  const job: ImportJob = {
    id: 'large',
    filename: 'large.pdf',
    period: '2026-11',
    status: 'review',
    account_id: 'card',
    error: '',
    source: { type: 'pdf', headers: [], preview: [] },
    rows,
  };
  vi.mocked(api).mockReset();
  vi.mocked(api).mockResolvedValue(job);
  render(
    <ImportReview
      initial={job}
      categories={[{ id: 'food', name: 'Food' }]}
      currency="USD"
      onClose={() => {}}
      onChanged={() => {}}
    />,
  );
  expect(screen.queryByLabelText('Description row 101')).toBeNull();
  fireEvent.change(screen.getByLabelText('Description row 1'), {
    target: { value: 'Edited store' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  expect(screen.getByLabelText('Description row 101')).toHaveValue('Store 101');
  fireEvent.click(screen.getByRole('button', { name: 'Previous page' }));
  expect(screen.getByLabelText('Description row 1')).toHaveValue(
    'Edited store',
  );
  fireEvent.click(screen.getByRole('button', { name: /save review/i }));
  await waitFor(() => expect(api).toHaveBeenCalled());
  const body = vi
    .mocked(api)
    .mock.calls.find(([path]) => path.endsWith('/review'))?.[2] as {
    rows: { description: string; source_index: number }[];
  };
  expect(body.rows).toHaveLength(201);
  expect(body.rows[0].description).toBe('Edited store');
  expect(body.rows[200].source_index).toBe(200);
});
