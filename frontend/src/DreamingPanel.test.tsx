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
