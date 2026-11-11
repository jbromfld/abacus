import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from './api';
import DreamingPanel from './DreamingPanel';
vi.mock('./api', () => ({ api: vi.fn() }));
vi.mock('./AdvisorMemory', () => ({ memoryChanged: vi.fn() }));

it('requires opt-in and exposes run and review controls', async () => {
  const state = { enabled: false, epoch: 'test', pending_review: 0, jobs: [] };
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (method === 'PUT') state.enabled = true;
    return { ...state };
  });
  render(<DreamingPanel />);
  await waitFor(() =>
    expect(screen.getByLabelText('Enable dreaming')).toBeEnabled(),
  );
  expect(screen.getByRole('button', { name: 'Dream now' })).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Enable dreaming'));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith('/advisor/dreaming', 'PUT', {
      enabled: true,
    }),
  );
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Dream now' })).toBeEnabled(),
  );
});

it('shows dreaming upgrade guidance without requiring memory changes', async () => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockResolvedValue({
    enabled: true,
    epoch: 'test',
    pending_review: 0,
    jobs: [
      {
        id: 'job',
        state: 'failed',
        reason:
          'Upgrade Babar for dreaming-controller-v1. Ordinary memory remains available.',
        groups: [],
      },
    ],
  });
  render(<DreamingPanel />);
  expect(
    await screen.findByText(/Ordinary memory remains available/),
  ).toBeVisible();
});

it('preserves review edits after Babar rejects a stale approval', async () => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (_path, method) => {
    if (method === 'POST')
      throw new Error('Memory changed; reload before saving.');
    return {
      enabled: true,
      epoch: 'test',
      pending_review: 1,
      jobs: [
        {
          id: 'job',
          state: 'review',
          reason: '',
          groups: [
            {
              operation_key: 'operation',
              state: 'review',
              note: { title: 'Original title', text: 'Suggested summary' },
              reasons: ['Review the dated constraints.'],
              evidence: [],
            },
          ],
        },
      ],
    };
  });
  render(<DreamingPanel />);
  const text = await screen.findByLabelText('Combined memory');
  fireEvent.change(text, { target: { value: 'My reviewed summary' } });
  fireEvent.click(
    screen.getByRole('button', { name: 'Approve consolidation' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent('Memory changed');
  expect(text).toHaveValue('My reviewed summary');
});
