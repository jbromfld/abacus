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
      purchases={[]}
      model="local"
      billPlan={null}
      revision={0}
      onOpenPlanner={() => {}}
    />,
  );
  const web = screen.getByRole('checkbox', {
    name: 'Use current web research',
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
  fireEvent.change(screen.getByLabelText(/Public research topic/), {
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
  fireEvent.change(screen.getByLabelText(/Public research topic/), {
    target: { value: 'Detroit July 2027' },
  });
  expect(
    screen.queryByRole('checkbox', {
      name: 'I approve sending these search terms to Brave.',
    }),
  ).not.toBeInTheDocument();
});
