import { useState } from 'react';
import Modal from './Modal';
export type Field = {
  name: string;
  label: string;
  type?: string;
  value?: string | number;
  options?: { value: string; label: string }[];
  required?: boolean;
  disabled?: boolean;
  hint?: string;
  min?: number;
  max?: number;
  showWhen?: Record<string, string>;
};
export type Editor = {
  title: string;
  description?: string;
  fields: Field[];
  submit: (data: Record<string, string>) => Promise<void>;
};
export default function FormEditor({
  editor,
  onClose,
  onSaved,
}: {
  editor: Editor;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      editor.fields.map((f) => [f.name, String(f.value ?? '')]),
    ),
  );
  return (
    <Modal title={editor.title} onClose={onClose}>
      <form
        onChange={(e) => {
          const target = e.target;
          if (
            target instanceof HTMLInputElement ||
            target instanceof HTMLSelectElement ||
            target instanceof HTMLTextAreaElement
          ) {
            const value =
              target instanceof HTMLInputElement && target.type === 'checkbox'
                ? String(target.checked)
                : target.value;
            if (target.name) setValues((v) => ({ ...v, [target.name]: value }));
          }
        }}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            const data = Object.fromEntries(
              new FormData(e.currentTarget).entries(),
            ) as Record<string, string>;
            await editor.submit(data);
            onSaved();
            onClose();
          } catch (e) {
            setError(String((e as Error).message));
          } finally {
            setBusy(false);
          }
        }}
      >
        {editor.description && <p className="muted">{editor.description}</p>}
        <div className="form-grid">
          {editor.fields
            .filter(
              (f) =>
                !f.showWhen ||
                Object.entries(f.showWhen).every(
                  ([key, value]) => values[key] === value,
                ),
            )
            .map((f) =>
              f.type === 'checkbox' ? (
                <label key={f.name} className="checkbox full">
                  <input
                    type="checkbox"
                    name={f.name}
                    defaultChecked={values[f.name] === 'true'}
                  />
                  <span>
                    {f.label}
                    {f.hint && <small>{f.hint}</small>}
                  </span>
                </label>
              ) : (
                <label
                  key={f.name}
                  className={f.type === 'textarea' ? 'full' : ''}
                >
                  {f.label}
                  {f.options ? (
                    <select
                      name={f.name}
                      defaultValue={f.value ?? ''}
                      required={f.required !== false}
                      disabled={f.disabled}
                    >
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  ) : f.type === 'textarea' ? (
                    <textarea name={f.name} defaultValue={f.value} />
                  ) : (
                    <input
                      name={f.name}
                      type={f.type ?? 'text'}
                      defaultValue={f.value}
                      required={f.required !== false}
                      disabled={f.disabled}
                      step={f.type === 'number' ? 'any' : undefined}
                      min={f.min ?? (f.type === 'number' ? '0' : undefined)}
                      max={f.max}
                    />
                  )}{' '}
                  {f.hint && <small>{f.hint}</small>}
                </label>
              ),
            )}
        </div>
        {error && (
          <p role="alert" className="notice danger">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  );
}
