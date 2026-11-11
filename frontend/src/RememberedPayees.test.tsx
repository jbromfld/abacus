import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api';
import RememberedPayees from './RememberedPayees';
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
const categories = [
  { id: 'food', name: 'Groceries' },
  { id: 'other', name: 'Other' },
];
const members = [
  {
    id: 'a',
    payee: 'wholefds ann arbor',
    kind: 'purchase',
    category_id: 'food',
    category: 'Groceries',
    group_id: null,
    group_name: null,
  },
  {
    id: 'b',
    payee: 'whole foods detroit',
    kind: 'purchase',
    category_id: 'other',
    category: 'Other',
    group_id: null,
    group_name: null,
  },
  {
    id: 'c',
    payee: 'wholefoods east',
    kind: 'purchase',
    category_id: 'food',
    category: 'Groceries',
    group_id: null,
    group_name: null,
  },
];
const review = {
  id: 'review',
  status: 'ready',
  progress: 1,
  total: 1,
  error: '',
  result: null,
  suggestions: [
    {
      id: 'suggestion',
      name: 'Whole Foods',
      kind: 'purchase',
      reason: 'Merchant spelling and location variants',
      members,
      member_ids: ['a', 'b', 'c'],
      category_conflict: true,
      suggested_category_id: null,
    },
  ],
};
const summary = { total: 3, groups: [], ungrouped: members, review: null };
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (path === '/payee-review/reviews' && method === 'POST') return review;
    if (path.endsWith('/apply'))
      return {
        ...review,
        status: 'applied',
        result: { updated_rule_count: 2, group_ids: ['group'] },
      };
    return summary;
  });
});
function mount() {
  const changed = vi.fn();
  render(
    <RememberedPayees
      categories={categories}
      model="local"
      revision={0}
      onChanged={changed}
    />,
  );
  fireEvent.click(screen.getByText(/Remembered payees/));
  return changed;
}
it('requires explicit selection, allows member exclusions and preserves individual categories by default', async () => {
  const changed = mount();
  fireEvent.click(
    await screen.findByRole('button', { name: 'Review similar payees' }),
  );
  const results = await screen.findByRole('region', {
    name: 'Suggested payee updates',
  });
  const apply = within(results).getByRole('button', {
    name: 'Apply selected changes (0)',
  });
  expect(apply).toBeDisabled();
  expect(api).not.toHaveBeenCalledWith(
    '/payee-review/reviews/review/apply',
    expect.anything(),
    expect.anything(),
  );
  fireEvent.click(
    await within(results).findByRole('checkbox', {
      name: 'Approve Whole Foods',
    }),
  );
  fireEvent.click(
    within(results).getByRole('checkbox', {
      name: 'Include wholefoods east in Whole Foods',
    }),
  );
  fireEvent.change(
    within(results).getByLabelText('Group name for Whole Foods'),
    { target: { value: 'Reviewed Whole Foods' } },
  );
  fireEvent.click(
    within(results).getByRole('button', { name: 'Apply selected changes (1)' }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      '/payee-review/reviews/review/apply',
      'POST',
      {
        groups: [
          {
            suggestion_id: 'suggestion',
            name: 'Reviewed Whole Foods',
            member_ids: ['a', 'b'],
            category_id: null,
          },
        ],
      },
    ),
  );
  expect(changed).toHaveBeenCalledOnce();
});
it('keeps edited review choices after a stale-preview rejection', async () => {
  const fallback = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (path.endsWith('/apply'))
      throw new Error('A selected payee changed. Nothing was applied.');
    return fallback(path, ...args);
  });
  const changed = mount();
  fireEvent.click(
    await screen.findByRole('button', { name: 'Review similar payees' }),
  );
  const approve = await screen.findByRole('checkbox', {
    name: 'Approve Whole Foods',
  });
  fireEvent.click(approve);
  fireEvent.change(screen.getByLabelText('Category change for Whole Foods'), {
    target: { value: 'food' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'Apply selected changes (1)' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Nothing was applied',
  );
  expect(screen.getByLabelText('Category change for Whole Foods')).toHaveValue(
    'food',
  );
  expect(changed).not.toHaveBeenCalled();
});
it('renders approved groups with their aliases and offers ungrouping without forgetting', async () => {
  const group = { id: 'group', name: 'Whole Foods', kind: 'purchase', members };
  vi.mocked(api).mockResolvedValue({
    ...summary,
    groups: [group],
    ungrouped: [],
  });
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  const changed = mount();
  fireEvent.click(await screen.findByText('Whole Foods', { exact: true }));
  expect(
    screen.getByRole('combobox', { name: 'Category for wholefds ann arbor' }),
  ).toHaveValue('food');
  fireEvent.click(screen.getByRole('button', { name: 'Ungroup' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith('/payee-review/groups/group', 'DELETE'),
  );
  expect(confirm).toHaveBeenCalled();
  expect(changed).toHaveBeenCalledOnce();
});
