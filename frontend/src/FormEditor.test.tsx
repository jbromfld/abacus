import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import FormEditor from './FormEditor';

it('retains conditional edits and submits the visible edited value', async () => {
  const submit = vi.fn().mockResolvedValue(undefined);
  render(
    <FormEditor
      editor={{
        title: 'Bill',
        fields: [
          {
            name: 'frequency',
            label: 'Frequency',
            value: 'annual',
            options: [
              { value: 'annual', label: 'Annual' },
              { value: 'monthly', label: 'Monthly' },
            ],
          },
          {
            name: 'due',
            label: 'Due month',
            value: '1',
            showWhen: { frequency: 'annual' },
          },
        ],
        submit,
      }}
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText('Due month'), {
    target: { value: '7' },
  });
  fireEvent.change(screen.getByLabelText('Frequency'), {
    target: { value: 'monthly' },
  });
  expect(screen.queryByLabelText('Due month')).toBeNull();
  fireEvent.change(screen.getByLabelText('Frequency'), {
    target: { value: 'annual' },
  });
  expect(screen.getByLabelText('Due month')).toHaveValue('7');
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith({ frequency: 'annual', due: '7' }),
  );
});
