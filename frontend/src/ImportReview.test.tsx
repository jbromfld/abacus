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
