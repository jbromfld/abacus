import { useState, useEffect, useRef } from 'react';
import { Check, Repeat2, Leaf, Plus, LoaderCircle, Trash2 } from 'lucide-react';
import { api, money, inputAmount, minor, digits } from './api';
import type { ImportJob, ReviewRow, Category, ImportUpdate } from './api';
import Modal from './Modal';
const kinds = ['purchase', 'refund', 'fee', 'payment', 'transfer'];
export default function ImportReview({
  initial,
  categories,
  currency,
  onClose,
  onChanged,
}: {
  initial: ImportJob;
  categories: Category[];
  currency: string;
  onClose: () => void;
  onChanged: (update?: ImportUpdate) => void;
}) {
  const [job, setJob] = useState(initial);
  const [rows, setRows] = useState<ReviewRow[]>(
    initial.rows.map((r, i) => ({ ...r, source_index: i })),
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = ['processing', 'committed', 'undone'].includes(job.status);
  const fmt = (n: number) => money(n, currency);
  const update = (j: ImportJob) => {
    setJob(j);
    setRows(j.rows.map((r, i) => ({ ...r, source_index: i })));
    onChanged(j);
  };
  const action = async (fn: () => Promise<ImportJob>) => {
    setBusy(true);
    setError('');
    try {
      update(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (job.status !== 'processing') return;
    const timer = setInterval(() => {
      api<ImportJob>('/imports/' + job.id)
        .then((j) => {
          setJob(j);
          if (j.status !== 'processing') {
            setRows(j.rows.map((r, i) => ({ ...r, source_index: i })));
            onChanged(j);
          }
        })
        .catch((e) => setError(e.message));
    }, 1500);
    return () => clearInterval(timer);
  }, [job.id, job.status]);
  const patch = (i: number, value: Partial<ReviewRow>) =>
    setRows((rs) =>
      rs.map((r, index) => (index === i ? { ...r, ...value } : r)),
    );
  const deleteImport = async () => {
    if (
      !window.confirm(
        'Delete this import and its review data? You can upload the same file again afterward.',
      )
    )
      return;
    setBusy(true);
    setError('');
    try {
      await api(`/imports/${job.id}`, 'DELETE');
      onChanged({ id: job.id, status: 'deleted' });
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  const saveReview = () =>
    api<ImportJob>(`/imports/${job.id}/review`, 'PUT', { rows });
  const skipped = rows.filter((r) => r.skip_duplicate).length;
  const selected = rows.filter((r) => r.selected && !r.skip_duplicate);
  const total = selected.reduce(
    (sum, r) =>
      sum +
      (r.kind === 'refund'
        ? -r.amount
        : ['purchase', 'fee'].includes(r.kind)
          ? r.amount
          : 0),
    0,
  );
  return (
    <Modal title="Review your statement" onClose={onClose}>
      <div className="review-heading">
        <p>
          <strong>{job.filename}</strong>
          <br />
          <span className="muted">
            {job.period} · {job.status}
          </span>
        </p>
        <span className="pill">{rows.length} proposed rows</span>
      </div>
      <p className="muted">
        Saved labels are remembered for future transactions with the same payee
        and type. Check dates, amounts, types, and categories against your
        statement. Zero-amount rows start unchecked and are excluded from
        saving. Rows whose original CSV fields match an earlier import for this
        card are always skipped. Possible duplicates within this file remain
        selectable.
      </p>
      {job.source.type === 'csv' &&
        !['committed', 'undone'].includes(job.status) && (
          <section className="csv-mapping">
            <h3>CSV columns & parsing</h3>
            <p className="muted">
              Confirm the columns below, then apply and remember them for this
              card.
            </p>
            {job.source.mapping_warning && (
              <p className="notice">{job.source.mapping_warning}</p>
            )}
            <form
              key={job.id + JSON.stringify(job.source.mapping)}
              onSubmit={(e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.currentTarget));
                void action(() =>
                  api(`/imports/${job.id}/mapping`, 'PUT', {
                    ...data,
                    positive_is: data.positive_is || null,
                  }),
                );
              }}
            >
              <div className="form-grid">
                {[
                  ['date_column', 'Date column'],
                  ['description_column', 'Description column'],
                  ['amount_column', 'Signed amount column'],
                ].map(([name, label]) => (
                  <label key={name}>
                    {label}
                    <select
                      name={name}
                      required
                      defaultValue={
                        job.source.mapping?.[name] ??
                        job.source.headers.find((h) =>
                          h.toLowerCase().includes(name.split('_')[0]),
                        ) ??
                        ''
                      }
                    >
                      <option value="">Choose column</option>
                      {job.source.headers.map((h) => (
                        <option key={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                ))}
                <label>
                  Date format
                  <select
                    name="date_format"
                    defaultValue={job.source.mapping?.date_format ?? '%Y-%m-%d'}
                  >
                    <option value="%Y-%m-%d">YYYY-MM-DD</option>
                    <option value="%m/%d/%Y">MM/DD/YYYY</option>
                    <option value="%d/%m/%Y">DD/MM/YYYY</option>
                    <option value="%m/%d/%y">MM/DD/YY</option>
                    <option value="%m/%d">MM/DD · year from period</option>
                  </select>
                </label>
                <label>
                  Initial transaction types
                  <select
                    name="positive_is"
                    defaultValue={job.source.mapping?.positive_is ?? ''}
                  >
                    <option value="">All purchases (default)</option>
                    <option value="purchase">
                      Positive = purchase; negative = refund
                    </option>
                    <option value="refund">
                      Negative = purchase; positive = refund
                    </option>
                  </select>
                </label>
              </div>
              <p className="muted">
                Rows start as purchases regardless of amount sign unless you
                select a sign convention. Review refunds and payments before
                saving. Map one signed amount column. Exports with separate
                debit/credit columns should be combined into one signed column
                first. Applying mapping replaces current review edits and
                remembers these settings for this card.
              </p>
              <button disabled={locked || busy}>
                <Check size={16} />
                Apply & remember mapping
              </button>
            </form>
            <details className="csv-source-preview">
              <summary>Preview original CSV columns</summary>
              <div className="table-scroll csv-preview">
                <table>
                  <caption>First five source rows</caption>
                  <thead>
                    <tr>
                      {job.source.headers.map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {job.source.preview.map((r, i) => (
                      <tr key={i}>
                        {job.source.headers.map((h) => (
                          <td key={h}>{r[h]}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
        )}
      {job.source.type === 'csv' &&
        ['committed', 'undone'].includes(job.status) && (
          <p className="notice">
            This statement is {job.status === 'committed' ? 'saved' : 'undone'}.
            To update this card’s CSV mapping, open an unfinished CSV import and
            choose Apply &amp; remember mapping.
          </p>
        )}
      {(error || job.error) && (
        <p role="alert" className="notice danger">
          {error || job.error}
        </p>
      )}
      {job.status === 'processing' && (
        <p className="notice">
          <LoaderCircle size={18} className="spin" />
          Processing locally. You can close this window and return later.
        </p>
      )}
      {!locked && (
        <div className="review-toolbar">
          <button
            className="secondary"
            disabled={busy || !rows.length}
            onClick={() =>
              void action(async () => {
                const validated = await saveReview();
                update(validated);
                return api(`/imports/${job.id}/categorize`, 'POST');
              })
            }
          >
            <Repeat2 size={16} />
            Apply remembered payees
          </button>
          <button
            className="secondary"
            hidden={job.source.type !== 'pdf'}
            disabled={busy}
            onClick={() => {
              if (
                rows.length &&
                !window.confirm(
                  'Re-extract this PDF? A successful extraction will replace your saved review edits. A failed extraction keeps them.',
                )
              )
                return;
              void action(async () => {
                if (rows.length) {
                  const validated = await saveReview();
                  update(validated);
                }
                return api(`/imports/${job.id}/process`, 'POST', {
                  replace_review: rows.length > 0,
                });
              });
            }}
          >
            <Leaf size={16} />
            Extract PDF transactions / retry
          </button>
          <button
            className="text-button"
            onClick={() =>
              setRows((r) => [
                ...r,
                {
                  date: job.period + '-01',
                  description: '',
                  amount: 0,
                  kind: 'purchase',
                  category_id: null,
                  selected: true,
                  errors: [],
                },
              ])
            }
          >
            <Plus size={16} />
            Add review row
          </button>
        </div>
      )}
      {rows.length > 0 && (
        <>
          <div className="review-table table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Save</th>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Amount ({currency})</th>
                  <th>Type</th>
                  <th>Category</th>
                  <th>Review notes</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={!r.selected ? 'unchecked' : ''}>
                    <td>
                      <input
                        aria-label={`Save row ${i + 1}`}
                        type="checkbox"
                        checked={r.selected}
                        disabled={locked || !!r.skip_duplicate}
                        onChange={(e) =>
                          patch(i, { selected: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`Date row ${i + 1}`}
                        type="date"
                        value={r.date}
                        disabled={locked || !!r.skip_duplicate}
                        onChange={(e) => patch(i, { date: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`Description row ${i + 1}`}
                        value={r.description}
                        disabled={locked || !!r.skip_duplicate}
                        onChange={(e) =>
                          patch(i, { description: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      <ReviewAmount
                        value={r.amount}
                        currency={currency}
                        disabled={locked || !!r.skip_duplicate}
                        onChange={(n) => patch(i, { amount: n })}
                      />
                    </td>
                    <td>
                      <select
                        aria-label={`Type row ${i + 1}`}
                        value={r.kind}
                        disabled={locked || !!r.skip_duplicate}
                        onChange={(e) => patch(i, { kind: e.target.value })}
                      >
                        {kinds.map((k) => (
                          <option key={k}>{k}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <select
                        aria-label={`Category row ${i + 1}`}
                        value={r.category_id ?? ''}
                        disabled={locked || !!r.skip_duplicate}
                        onChange={(e) =>
                          patch(i, { category_id: e.target.value || null })
                        }
                      >
                        <option value="">Choose category</option>
                        {categories.map((c) => (
                          <option value={c.id} key={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {r.classification === 'remembered_payee' && (
                        <span className="pill included">Remembered payee</span>
                      )}
                      {r.classification === 'normalized_payee' && (
                        <span className="pill included">
                          Matched normalized payee
                        </span>
                      )}
                      {r.classification === 'similar_payee' && (
                        <span className="pill warning">
                          Similar payee · check category
                        </span>
                      )}
                      {r.classification === 'description_keyword' && (
                        <span className="pill">PAYMENT in description</span>
                      )}
                      {r.skip_duplicate ? (
                        <span className="pill warning">
                          Already imported · skipped
                        </span>
                      ) : (
                        r.duplicate && (
                          <span className="pill warning">
                            Possible duplicate
                          </span>
                        )
                      )}
                      {(!r.skip_duplicate ? r.errors : [])?.map((e, j) => (
                        <small className="red" key={j}>
                          {e}
                        </small>
                      ))}
                      {r.source && (
                        <details>
                          <summary>Source</summary>
                          <pre>{JSON.stringify(r.source, null, 2)}</pre>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="review-total">
            <span>
              {selected.length} selected
              {skipped ? ` · ${skipped} already imported, will skip` : ''} · net
              spending
            </span>
            <strong>{fmt(total)}</strong>
          </div>
        </>
      )}
      {job.status === 'committed' && job.commit_summary && (
        <p className="notice" role="status">
          Saved {job.commit_summary.added} transactions. Skipped{' '}
          {job.commit_summary.skipped} rows already imported for this card.
        </p>
      )}
      <div className="modal-actions">
        <button
          className="secondary red"
          disabled={
            busy || job.status === 'processing' || job.status === 'committed'
          }
          title={
            job.status === 'committed'
              ? 'Undo this import before deleting it'
              : job.status === 'processing'
                ? 'Wait for processing to finish'
                : undefined
          }
          onClick={() => void deleteImport()}
        >
          <Trash2 size={16} />
          Delete import
        </button>
        {job.status === 'committed' ? (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  'Undo this import? All transactions attached to it, including edits, will be removed.',
                )
              )
                void action(() => api(`/imports/${job.id}/undo`, 'POST'));
            }}
          >
            Undo import
          </button>
        ) : job.status === 'undone' ? (
          <p>
            This import has been undone. Delete it to upload the same file
            again.
          </p>
        ) : (
          <>
            <button
              className="secondary"
              disabled={locked || busy}
              onClick={() => void action(saveReview)}
            >
              Validate & save review
            </button>
            <button
              disabled={
                locked ||
                busy ||
                !rows.some((r) => r.selected || r.skip_duplicate)
              }
              onClick={() =>
                void action(async () => {
                  const validated = await saveReview();
                  update(validated);
                  return api(`/imports/${job.id}/commit`, 'POST');
                })
              }
            >
              <Check size={16} />
              {!selected.length && skipped
                ? 'Finish import'
                : 'Save selected transactions'}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}
function ReviewAmount({
  value,
  currency,
  disabled,
  onChange,
}: {
  value: number;
  currency: string;
  disabled: boolean;
  onChange: (n: number) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [text, setText] = useState(inputAmount(value, currency));
  useEffect(() => {
    if (document.activeElement !== ref.current)
      setText(inputAmount(value, currency));
  }, [value, currency]);
  return (
    <input
      ref={ref}
      aria-label="Transaction amount"
      type="number"
      step={digits(currency) === 0 ? '1' : '0.01'}
      min="0"
      value={text}
      disabled={disabled}
      onChange={(e) => {
        setText(e.target.value);
        try {
          onChange(minor(e.target.value, currency));
        } catch {
          onChange(0);
        }
      }}
    />
  );
}
