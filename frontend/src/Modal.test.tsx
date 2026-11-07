import { render, screen, fireEvent } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Modal from './Modal';
it('names the dialog from its heading and handles cancel', () => {
  const close = vi.fn();
  render(
    <Modal title="Review your statement" onClose={close}>
      <button>Save</button>
    </Modal>,
  );
  const dialog = screen.getByRole('dialog', { name: 'Review your statement' });
  expect(dialog).toHaveAttribute('open');
  fireEvent(dialog, new Event('cancel', { bubbles: true, cancelable: true }));
  expect(close).toHaveBeenCalledOnce();
});
