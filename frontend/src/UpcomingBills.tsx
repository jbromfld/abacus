import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CalendarDays,
  Check,
  LoaderCircle,
  Pencil,
  Plus,
  RotateCcw,
  AlertTriangle,
} from 'lucide-react';
import { api, money } from './api';
import type { BillOccurrence, Category, DueSummary } from './api';
import Modal from './Modal';

const dayLabel = (value: string) =>
  new Date(value + 'T12:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

export default function UpcomingBills({
  currency,
  categories,
  revision,
  onEdit,
  onAdd,
  onChanged,
}: {
  currency: string;
  categories: Category[];
  revision: number;
  onEdit: (id: string) => void;
  onAdd: () => void;
  onChanged: () => void;
}) {
  const [data, setData] = useState<DueSummary | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [unpaidOnly, setUnpaidOnly] = useState(false);
  const [confirm, setConfirm] = useState<BillOccurrence | null>(null);
  const [paidOn, setPaidOn] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const [historyLimit, setHistoryLimit] = useState(10);
  const [overdueLimit, setOverdueLimit] = useState(10);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const id = ++sequence.current;
    try {
      const value = await api<DueSummary>(
        '/recurring/dues',
        'GET',
        undefined,
        abort.signal,
      );
      if (id === sequence.current) {
        setData(value);
        setError('');
      }
    } catch (e) {
      if (id === sequence.current && (e as Error).name !== 'AbortError')
        setError((e as Error).message);
    } finally {
      if (id === sequence.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 60000);
    const visible = () => {
      if (!document.hidden) void load();
    };
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('focus', visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('focus', visible);
      sequence.current++;
      controller.current?.abort();
    };
  }, [revision, load]);
  const openPaid = (bill: BillOccurrence) => {
    setConfirmError('');
    setPaidOn(bill.paid_on ?? data!.today);
    setConfirm(bill);
  };
  const save = async (bill: BillOccurrence, paid: boolean) => {
    setBusy(true);
    setConfirmError('');
    setError('');
    try {
      await api(
        `/recurring/${bill.recurring_id}/payments/${bill.period}`,
        'PUT',
        { paid, paid_on: paid ? paidOn : null },
      );
      setConfirm(null);
      await load();
      onChanged();
    } catch (e) {
      if (paid) setConfirmError((e as Error).message);
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const upcoming = (data?.monthly_upcoming ?? []).filter(
    (bill) => !unpaidOnly || !bill.paid,
  );
  const overdue = (data?.monthly_overdue ?? []).filter(
    (bill) => !unpaidOnly || !bill.paid,
  );
  const row = (bill: BillOccurrence, label?: string) => (
    <li className="bill-row" key={bill.recurring_id + bill.period}>
      <div className={'bill-date ' + (bill.status === 'overdue' ? 'red' : '')}>
        <CalendarDays size={16} />
        <strong>{dayLabel(bill.due_date)}</strong>
        <small>
          {bill.paid
            ? bill.paid_source === 'ach'
              ? 'Paid by ACH'
              : 'Paid'
            : bill.automatic
              ? 'Scheduled ACH'
              : bill.status === 'overdue'
                ? 'Overdue · unconfirmed'
                : bill.status === 'today'
                  ? 'Due today'
                  : 'Scheduled'}
        </small>
      </div>
      <div className="bill-description">
        <strong>{label ?? bill.name}</strong>
        <small>
          {categories.find((c) => c.id === bill.category_id)?.name ?? 'Other'}
        </small>
        {bill.paid_on && <small>Paid {dayLabel(bill.paid_on)}</small>}
        {bill.confirmed_due_date &&
          bill.confirmed_due_date !== bill.due_date && (
            <small>
              Confirmed against due date {dayLabel(bill.confirmed_due_date)}
            </small>
          )}
        {bill.automatic && (
          <small className="ach-label">
            {bill.ach_recorded
              ? 'Automatically recorded ACH debit'
              : 'Automatic ACH · no manual confirmation needed'}
          </small>
        )}
      </div>
      <strong className="bill-amount">{money(bill.amount, currency)}</strong>
      <div className="bill-actions">
        {bill.automatic ? (
          <span className="pill included">Automatic ACH</span>
        ) : bill.paid ? (
          <>
            <button
              className="text-button"
              disabled={busy}
              aria-label={`Correct paid date for ${bill.name}, ${bill.period}`}
              onClick={() => openPaid(bill)}
            >
              Edit paid date
            </button>
            <button
              className="text-button"
              disabled={busy}
              aria-label={`Mark ${bill.name}, ${bill.period} unpaid`}
              onClick={() => void save(bill, false)}
            >
              <RotateCcw size={13} />
              Mark unpaid
            </button>
          </>
        ) : (
          <button
            className="secondary small bill-mark-paid"
            disabled={busy}
            aria-label={`Mark ${bill.name}, ${bill.period} paid`}
            onClick={() => openPaid(bill)}
          >
            <Check size={14} />
            Mark paid
          </button>
        )}
        <button
          className="icon"
          disabled={busy}
          aria-label={`Edit due date for ${bill.name}`}
          onClick={() => onEdit(bill.recurring_id)}
        >
          <Pencil size={14} />
        </button>
      </div>
    </li>
  );
  return (
    <div className="due-panels">
      <section className="panel upcoming-bills">
        <div className="section-head">
          <div>
            <h2>Upcoming monthly bills</h2>
            <p>
              {data
                ? `${dayLabel(data.today)} – ${dayLabel(data.through)} · based on today, independent of the budget month`
                : 'The next 30 days, starting today.'}
            </p>
          </div>
          <button className="text-button" onClick={onAdd}>
            <Plus size={16} />
            Add bill
          </button>
        </div>
        <label className="checkbox bill-unpaid-filter">
          <input
            type="checkbox"
            checked={unpaidOnly}
            onChange={(event) => setUnpaidOnly(event.target.checked)}
          />
          Unpaid only
        </label>
        {loading && !data && (
          <p className="bill-empty" role="status">
            <LoaderCircle size={16} className="spin" />
            Loading due dates…
          </p>
        )}
        {error && (
          <div className="notice danger" role="alert">
            <AlertTriangle size={16} />
            {error}
            <button className="text-button" onClick={() => void load()}>
              Retry
            </button>
          </div>
        )}
        {data && (
          <>
            {overdue.length > 0 && (
              <div className="bill-overdue">
                <h3>
                  Overdue monthly bills <span>({overdue.length})</span>
                </h3>
                <ul className="bill-list">
                  {overdue.slice(0, overdueLimit).map((b) => row(b))}
                </ul>
                {overdue.length > overdueLimit && (
                  <button
                    className="text-button"
                    onClick={() => setOverdueLimit((n) => n + 20)}
                  >
                    Show more overdue bills
                  </button>
                )}
              </div>
            )}
            {upcoming.length ? (
              <ul className="bill-list">{upcoming.map((b) => row(b))}</ul>
            ) : (
              <p className="bill-empty">
                {unpaidOnly
                  ? 'No unpaid monthly bills with due dates in the next 30 days.'
                  : 'No monthly bills with due dates in the next 30 days.'}
              </p>
            )}
          </>
        )}
        <div className="panel-foot">
          ACH bills are tracked automatically. Budget allowances do not need due
          dates. Manual paid confirmations do not change actual spending.
        </div>
      </section>
      <section className="panel annual-bills">
        <div className="section-head">
          <div>
            <h2>Annual expenses</h2>
            <p>
              Annual bills and budget allowances · separate from the
              next-30-days list.
            </p>
          </div>
        </div>
        {data?.annual.length
          ? data.annual.map((b) => (
              <article className="annual-bill" key={b.recurring_id}>
                <div className="annual-bill-title">
                  <div>
                    <h3>{b.name}</h3>
                    <small>
                      {b.allowance
                        ? 'Budget allowance · no payment due date'
                        : b.distribute_annual
                          ? 'Budget distributed across 12 months'
                          : 'Budget counted in the due month'}
                    </small>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => onEdit(b.recurring_id)}
                  >
                    <Pencil size={13} />
                    {b.allowance ? 'Edit budget' : 'Edit'}
                  </button>
                </div>
                {b.allowance ? (
                  <div className="annual-allowance">
                    <span>
                      Annual budget
                      <strong>{money(b.annual_amount, currency)}</strong>
                    </span>
                    {b.monthly_allocation !== null ? (
                      <span>
                        Monthly allocation
                        <strong>{money(b.monthly_allocation, currency)}</strong>
                      </span>
                    ) : (
                      <small>
                        Use “Distribute annual expense across 12 months” to
                        spread this budget monthly.
                      </small>
                    )}
                    <p>
                      Actual spending comes from your transactions; this
                      allowance needs no paid confirmation.
                    </p>
                  </div>
                ) : (
                  <>
                    {b.overdue_count > 0 && (
                      <div className="bill-overdue">
                        <h4>
                          {b.overdue_count} overdue annual{' '}
                          {b.overdue_count === 1 ? 'payment' : 'payments'}
                        </h4>
                        <ul className="bill-list">
                          {row(b.overdue[0], 'Oldest unconfirmed payment')}
                        </ul>
                        {b.overdue.length > 1 && (
                          <details>
                            <summary>
                              Other overdue annual payments (
                              {b.overdue.length - 1})
                            </summary>
                            <ul className="bill-list">
                              {b.overdue.slice(1).map((p) => row(p))}
                            </ul>
                          </details>
                        )}
                      </div>
                    )}
                    {b.next ? (
                      <ul className="bill-list">
                        {row(b.next, 'Next annual payment')}
                      </ul>
                    ) : (
                      <p className="bill-empty">
                        No further payment falls within this schedule.
                      </p>
                    )}
                  </>
                )}
              </article>
            ))
          : data && (
              <p className="bill-empty">No active annual expenses yet.</p>
            )}
      </section>
      {data && data.paid_history.length > 0 && (
        <section className="panel bill-history">
          <details>
            <summary>Payment history ({data.paid_history.length})</summary>
            <p className="muted">
              Manual confirmations retain their recorded dates and amounts. ACH
              payments use their recorded actual transactions.
            </p>
            <ul className="bill-list">
              {data.paid_history.slice(0, historyLimit).map((p) => row(p))}
            </ul>
            {data.paid_history.length > historyLimit && (
              <button
                className="text-button"
                onClick={() => setHistoryLimit((n) => n + 20)}
              >
                Show more payments
              </button>
            )}
          </details>
        </section>
      )}
      {confirm && (
        <Modal
          title={confirm.paid ? 'Correct paid date' : 'Confirm bill paid'}
          onClose={() => {
            if (!busy) setConfirm(null);
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void save(confirm, true);
            }}
          >
            <p>
              <strong>{confirm.name}</strong> ·{' '}
              {money(confirm.amount, currency)}
              <br />
              Scheduled for {dayLabel(confirm.due_date)}
            </p>
            <p className="muted">
              This confirmation does not create or change a spending
              transaction.
            </p>
            {confirm.ach_recorded && (
              <p className="notice">
                An ACH debit was recorded from the schedule. Confirm it against
                your bank records.
              </p>
            )}
            <label>
              Paid on
              <input
                type="date"
                required
                min="1900-01-01"
                max={data?.today}
                value={paidOn}
                onChange={(e) => setPaidOn(e.target.value)}
                disabled={busy}
              />
            </label>
            {confirmError && (
              <p className="notice danger" role="alert">
                {confirmError}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              <button disabled={busy || !paidOn}>
                <Check size={15} />
                {busy ? 'Saving…' : 'Confirm paid'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
