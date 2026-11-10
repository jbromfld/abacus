import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import AdvisorMemory, { RememberExchange } from './AdvisorMemory';

vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
const note = {
  id: 'note-1',
  revision: 1,
  title: 'Discretionary savings',
  text: 'I intend to reduce spending by USD 50/month.',
  kind: 'intention',
  source_date: '2026-11-08',
  source_excerpt: 'I intend to cut USD 50/month.',
  cues: ['savings'],
  status: 'active',
};
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/advisor/memory/status')
      return { message: 'Local Memora connected.' };
    if (path === '/advisor/memory') return { items: [note], next_offset: null };
    if (path === '/advisor/memory/draft') {
      const { id: _id, revision: _revision, ...draft } = note;
      return { note: draft, warning: 'Review your intention.' };
    }
    return { ...note, history: [note] };
  });
});
it('does not contact Memora while disabled', () => {
  render(<AdvisorMemory enabled={false} />);
  expect(screen.getByText(/Advisor memory is off/)).toBeInTheDocument();
  expect(vi.mocked(api)).not.toHaveBeenCalled();
});
it('drafts locally but only saves after explicit approval, preserving edits on failure', async () => {
  render(
    <RememberExchange user="Cut USD 50/month" assistant="A recommendation" />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Remember this' }));
  await screen.findByDisplayValue(note.text);
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path === '/advisor/memory'),
  ).toBe(false);
  fireEvent.change(screen.getByLabelText('Note'), {
    target: { value: 'My approved savings intention.' },
  });
  vi.mocked(api).mockRejectedValueOnce(new Error('Local memory unavailable'));
  fireEvent.click(screen.getByRole('button', { name: 'Save memory' }));
  await screen.findByText('Local memory unavailable');
  expect(screen.getByLabelText('Note')).toHaveValue(
    'My approved savings intention.',
  );
  const firstKey = vi
    .mocked(api)
    .mock.calls.find(
      ([path, method]) => path === '/advisor/memory' && method === 'POST',
    )?.[2];
  vi.mocked(api).mockResolvedValueOnce(note);
  fireEvent.click(screen.getByRole('button', { name: 'Save memory' }));
  await waitFor(() =>
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
  );
  expect(
    vi
      .mocked(api)
      .mock.calls.filter(
        ([path, method]) => path === '/advisor/memory' && method === 'POST',
      )
      .at(-1)?.[2],
  ).toEqual(firstKey);
});
it('requires a separate forget confirmation and clears local advisor context', async () => {
  const changed = vi.fn();
  window.addEventListener('abacus-memory-changed', changed);
  render(<AdvisorMemory enabled />);
  fireEvent.click(
    await screen.findByRole('button', { name: /Edit “Discretionary savings”/ }),
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Forget note' }));
  expect(
    vi.mocked(api).mock.calls.some(([, method]) => method === 'DELETE'),
  ).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Confirm forget' }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(
    vi
      .mocked(api)
      .mock.calls.some(
        ([path, method]) =>
          path.includes('expected_revision=1') && method === 'DELETE',
      ),
  ).toBe(true);
  window.removeEventListener('abacus-memory-changed', changed);
});
