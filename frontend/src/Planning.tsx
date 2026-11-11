import { useEffect, useRef, useState } from 'react';
import {
  Plus,
  Pencil,
  Trash2,
  MessageCircle,
  CalendarDays,
} from 'lucide-react';
import { api, inputAmount, minor, money } from './api';
import AmountSlider from './AmountSlider';
import SavingsSettings from './SavingsSettings';
import Modal from './Modal';

export type PlanDraft = {
  id?: string;
  warning?: string;
  name?: string;
  amount?: number | null;
  target_date?: string | null;
  category_id?: string | null;
  recurring_id?: string | null;
  date_from_bill?: boolean;
};
export type PlanItem = {
  id: string;
  name: string;
  amount: number;
  target_date: string;
  category_id: string | null;
  category: string | null;
  recurring_id: string | null;
  recurring_name: string | null;
  set_aside: number | null;
  still_needed: number | null;
  monthly_needed: number | null;
  status: string;
  contribution_count: number;
  monthly_allocation?: number;
  projected_contributions?: number;
  projected_funding?: number | null;
  funding_gap?: number | null;
};
export type PlanningData = {
  savings: number | null;
  savings_month: string | null;
  floor: number;
  total_planned: number;
  set_aside: number | null;
  free_savings: number | null;
  basis: string;
  plans: PlanItem[];
  categories: { id: string; name: string }[];
  annual_expenses: {
    id: string;
    name: string;
    amount: number;
    target_date: string;
    plan_id?: string | null;
    date_from_bill?: boolean;
  }[];
  projection: null | {
    basis: string;
    income_complete: boolean;
    months: { month: string; balance: number | null; plan_payments: number }[];
  };
};
const dateLabel = (date: string) =>
  new Date(date + 'T12:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

function PlanForm({
  data,
  initial,
  currency,
  onClose,
  onSave,
  chooseAnnual = false,
}: {
  data: PlanningData;
  initial: PlanDraft & { id?: string };
  currency: string;
  onClose: () => void;
  onSave: () => void;
  chooseAnnual?: boolean;
}) {
  const [planId, setPlanId] = useState(initial.id);
  const [name, setName] = useState(initial.name ?? '');
  const [amount, setAmount] = useState(
    initial.amount ? inputAmount(initial.amount, currency) : '',
  );
  const [target, setTarget] = useState(initial.target_date ?? '');
  const [category, setCategory] = useState(
    initial.category_id ??
      data.categories.find((c) => c.id === 'purchase')?.id ??
      '',
  );
  const [recurring, setRecurring] = useState(initial.recurring_id ?? null);
  const [dateFromBill, setDateFromBill] = useState(
    initial.date_from_bill ?? !!initial.recurring_id,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRef(crypto.randomUUID());
  return (
    <Modal title={planId ? 'Edit plan' : 'Add a plan'} onClose={onClose}>
      <form
        className="plan-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            await api(
              '/planning' + (planId ? '/' + planId : ''),
              planId ? 'PUT' : 'POST',
              {
                name,
                amount: minor(amount, currency),
                target_date: target,
                category_id: category || null,
                recurring_id: recurring,
                ...(!planId ? { request_id: requestId.current } : {}),
              },
            );
            onSave();
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {initial.warning && <p className="notice">{initial.warning}</p>}
        {(chooseAnnual || initial.id) && (
          <label>
            Use an annual expense
            <select
              aria-label="Use an annual expense"
              value={recurring ?? ''}
              disabled={busy}
              onChange={(e) => {
                const source = data.annual_expenses.find(
                  (item) => item.id === e.target.value,
                );
                if (!source) {
                  setRecurring(null);
                  return;
                }
                const existing = data.plans.find(
                  (p) => p.id === source.plan_id,
                );
                setPlanId(initial.id ?? existing?.id);
                setRecurring(source.id);
                setName(existing?.name ?? source.name);
                setAmount(inputAmount(source.amount, currency));
                setTarget(
                  source.date_from_bill === false ? '' : source.target_date,
                );
                setDateFromBill(source.date_from_bill !== false);
                setCategory(
                  data.categories.find((c) => c.id === 'tax')?.id ?? '',
                );
              }}
            >
              <option value="">Independent plan</option>
              {recurring &&
                !data.annual_expenses.some((p) => p.id === recurring) && (
                  <option value={recurring}>{initial.name} (linked)</option>
                )}
              {data.annual_expenses.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                  disabled={
                    !!initial.id &&
                    !!item.plan_id &&
                    item.plan_id !== initial.id
                  }
                >
                  {item.name}
                  {item.plan_id ? ' · already tracked' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Name
          <input
            autoFocus
            aria-label="Plan name"
            required
            maxLength={160}
            value={name}
            disabled={busy}
            placeholder="Fall vacation"
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <AmountSlider
          label="Target amount"
          currency={currency}
          value={amount}
          onChange={setAmount}
          disabled={busy || !!recurring}
        />
        <div className="form-grid">
          <label>
            Target date
            <input
              aria-label="Target date"
              type="date"
              min="1900-01-01"
              max="9998-12-31"
              required
              value={target}
              disabled={busy || (!!recurring && dateFromBill)}
              onChange={(e) => setTarget(e.target.value)}
            />
          </label>
          <label>
            Category
            <select
              aria-label="Planning category"
              value={category}
              disabled={busy}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">Uncategorized</option>
              {data.categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {recurring && (
          <p className="muted">
            Linked annual expense:{' '}
            {data.annual_expenses.find((item) => item.id === recurring)?.name ??
              initial.name}
            . The amount follows the annual bill automatically.{' '}
            {dateFromBill
              ? 'The date also follows the bill. Edit them in Recurring accounts.'
              : 'This bill has no due date; choose a target date here.'}
          </p>
        )}
        {error && (
          <p className="notice danger" role="alert">
            {error}
          </p>
        )}
        <div className="button-group">
          <button disabled={busy}>{busy ? 'Saving…' : 'Save plan'}</button>
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function Planning({
  currency,
  revision,
  onChanged,
  onDiscuss,
  onDeleted,
  initialDraft,
  onDraftUsed,
  advisorEnabled = true,
}: {
  currency: string;
  revision: number;
  onChanged: () => void;
  onDiscuss: (id: string) => void;
  onDeleted: (id: string) => void;
  initialDraft?: { key: number; value: PlanDraft } | null;
  onDraftUsed: () => void;
  advisorEnabled?: boolean;
}) {
  const [data, setData] = useState<PlanningData | null>(null);
  const [error, setError] = useState('');
  const [editor, setEditor] = useState<(PlanDraft & { id?: string }) | null>(
    null,
  );
  const [annual, setAnnual] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const read = () =>
      api<PlanningData>('/planning')
        .then((value) => {
          if (active) {
            setData(value);
            setError('');
          }
        })
        .catch((e) => active && setError(e.message));
    void read();
    const timer = setInterval(() => void read(), 60000);
    window.addEventListener('focus', read);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener('focus', read);
    };
  }, [revision]);
  useEffect(() => {
    if (initialDraft) {
      setEditor(initialDraft.value);
      setAnnual(false);
      onDraftUsed();
    }
  }, [initialDraft, onDraftUsed]);
  const fmt = (n: number | null) =>
    n === null ? 'Not set' : money(n, currency);
  const remove = async (item: PlanItem) => {
    if (
      !window.confirm(
        `Permanently delete ${item.name}? This removes its earmark. Bills, savings and transactions remain. This cannot be undone.`,
      )
    )
      return;
    setBusy(item.id);
    setError('');
    try {
      await api('/planning/' + item.id, 'DELETE');
      setData((previous) =>
        previous
          ? {
              ...previous,
              plans: previous.plans.filter((row) => row.id !== item.id),
            }
          : null,
      );
      onDeleted(item.id);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="planning-page">
      {error && (
        <p role="alert" className="notice danger">
          {error}
        </p>
      )}
      {!data ? (
        <p role="status">Loading planning…</p>
      ) : (
        <>
          <div className="stats planning-totals">
            <div className="stat">
              <span className="stat-label">Savings</span>
              <strong>{fmt(data.savings)}</strong>
              <small>
                {data.savings_month
                  ? `Opening balance · ${data.savings_month}`
                  : 'Set your savings below'}
              </small>
            </div>
            <div className="stat">
              <span className="stat-label">Planned</span>
              <strong>{fmt(data.total_planned)}</strong>
              <small>
                {data.plans.length} plans · {fmt(data.set_aside)} set aside
              </small>
            </div>
            <div className="stat balance">
              <span className="stat-label">Unassigned savings</span>
              <strong>{fmt(data.free_savings)}</strong>
              <small>After plans and your protected savings floor</small>
            </div>
          </div>
          <details className="panel planning-savings">
            <summary>Savings balance & slider</summary>
            <SavingsSettings currency={currency} onChanged={onChanged} />
          </details>
          <section className="panel">
            <div className="section-head">
              <div>
                <h2>Your plans</h2>
                <p>
                  A name, an amount, and a date. Your savings does the rest.
                </p>
              </div>
              <div className="button-group">
                <button
                  onClick={() => {
                    setEditor({});
                    setAnnual(false);
                  }}
                >
                  <Plus size={16} />
                  Add a plan
                </button>
                {data.annual_expenses.length > 0 && (
                  <button
                    className="secondary"
                    onClick={() => {
                      setEditor({});
                      setAnnual(true);
                    }}
                  >
                    Use annual expense
                  </button>
                )}
              </div>
            </div>
            {!data.plans.length ? (
              <div className="empty">
                <CalendarDays size={30} />
                <h3>What are you making room for?</h3>
                <p>Add winter tax, a vacation, or your next purchase.</p>
              </div>
            ) : (
              <div className="plan-list">
                {data.plans.map((item) => (
                  <article className="plan-card" key={item.id}>
                    <div className="plan-card-heading">
                      <div>
                        <span className="pill">
                          {item.category ?? 'Uncategorized'}
                        </span>
                        <h3>{item.name}</h3>
                        <p>
                          Target · {dateLabel(item.target_date)}
                          {item.recurring_id ? ' · linked annual bill' : ''}
                        </p>
                      </div>
                      <strong>{fmt(item.amount)}</strong>
                    </div>
                    <progress
                      aria-label={`${item.name} funding progress`}
                      value={item.set_aside ?? 0}
                      max={item.amount}
                    />
                    <div className="plan-progress">
                      <span>
                        {item.set_aside === null
                          ? 'Set savings to track funding'
                          : `${fmt(item.set_aside)} set aside · ${fmt(item.still_needed)} to go`}
                      </span>
                      {item.status === 'paid' || item.status === 'inactive' ? (
                        <strong>
                          {item.status === 'paid'
                            ? 'Paid'
                            : 'Bill no longer scheduled'}
                        </strong>
                      ) : item.status === 'funded' ? (
                        <strong>Funded</strong>
                      ) : item.status === 'overdue' ? (
                        <strong className="red">Past target date</strong>
                      ) : (
                        item.monthly_needed !== null && (
                          <span>
                            {fmt(item.monthly_needed)}
                            {item.contribution_count === 0
                              ? ' needed now'
                              : item.recurring_id
                                ? ' extra / month needed'
                                : ' / month suggested'}
                          </span>
                        )
                      )}
                    </div>
                    {item.monthly_allocation !== undefined && (
                      <AnnualFunding item={item} currency={currency} />
                    )}
                    <div className="button-group">
                      <button
                        className="secondary small"
                        onClick={() => onDiscuss(item.id)}
                      >
                        <MessageCircle size={14} />
                        {advisorEnabled ? 'Discuss' : 'Set up advisor'}
                      </button>
                      <button
                        className="text-button"
                        aria-label={`Edit ${item.name}`}
                        onClick={() => {
                          setEditor(item);
                          setAnnual(false);
                        }}
                      >
                        <Pencil size={14} />
                        Edit
                      </button>
                      <button
                        className="text-button red"
                        aria-label={`Permanently delete ${item.name}`}
                        disabled={busy === item.id}
                        onClick={() => void remove(item)}
                      >
                        <Trash2 size={14} />
                        Delete
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            <p className="planning-note">
              Savings is shared across plans by earliest target date. Suggested
              monthly amounts are goals, not confirmed transfers. Imported
              spending and bill schedules stay separate.
            </p>
          </section>
          {data.projection && (
            <details className="panel planning-projection">
              <summary>See the funding projection</summary>
              <p>{data.projection.basis}</p>
              {!data.projection.income_complete && (
                <p className="notice">
                  Income is missing in some months. This projection is
                  incomplete.
                </p>
              )}
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Plan payments</th>
                      <th>Projected savings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.projection.months.map((row) => (
                      <tr key={row.month}>
                        <th>{row.month}</th>
                        <td>{fmt(row.plan_payments)}</td>
                        <td
                          className={
                            row.balance !== null && row.balance < data.floor
                              ? 'red'
                              : ''
                          }
                        >
                          {fmt(row.balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          {editor && (
            <PlanForm
              key={editor.id ?? initialDraft?.key ?? 'new'}
              initial={editor}
              data={data}
              currency={currency}
              chooseAnnual={annual}
              onClose={() => setEditor(null)}
              onSave={onChanged}
            />
          )}
        </>
      )}
    </div>
  );
}

export function PlanningCategories({
  revision,
  onChanged,
}: {
  revision: number;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<{ id: string; name: string }[]>([]);
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api<typeof items>('/planning/categories')
      .then((rows) => active && setItems(rows))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [revision]);
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try {
      await action();
      onChanged();
      setEditing(null);
      setName('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>Planning categories</h2>
          <p>Labels for your tax, vacation and purchase goals.</p>
        </div>
      </div>
      {items.map((item) => (
        <div className="name-row" key={item.id}>
          <strong className="grow">{item.name}</strong>
          <button
            className="icon"
            disabled={busy}
            aria-label={`Rename planning category ${item.name}`}
            onClick={() => {
              setEditing(item.id);
              setName(item.name);
            }}
          >
            <Pencil size={15} />
          </button>
          <button
            className="icon"
            disabled={busy}
            aria-label={`Delete planning category ${item.name}`}
            onClick={() => {
              if (
                window.confirm(
                  `Delete category ${item.name}? Its plans will become uncategorized.`,
                )
              )
                void perform(() =>
                  api('/planning/categories/' + item.id, 'DELETE'),
                );
            }}
          >
            <Trash2 size={15} />
          </button>
        </div>
      ))}
      <form
        className="planning-category-form"
        onSubmit={(e) => {
          e.preventDefault();
          void perform(() =>
            api(
              '/planning/categories' + (editing ? '/' + editing : ''),
              editing ? 'PUT' : 'POST',
              { name },
            ),
          );
        }}
      >
        <input
          aria-label="Planning category name"
          placeholder="New category"
          required
          maxLength={80}
          value={name}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
        />
        <button disabled={busy}>{editing ? 'Rename' : 'Add'}</button>
        {editing && (
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setEditing(null);
              setName('');
            }}
          >
            Cancel
          </button>
        )}
      </form>
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

export function AnnualFunding({
  item,
  currency,
}: {
  item: PlanItem;
  currency: string;
}) {
  const fmt = (value: number | null | undefined) =>
    value == null ? 'Not set' : money(value, currency);
  return (
    <div className="annual-funding">
      <dl className="annual-funding-values">
        <div>
          <dt>Budgeted monthly</dt>
          <dd>{fmt(item.monthly_allocation)}</dd>
        </div>
        <div>
          <dt>Set aside now</dt>
          <dd>{fmt(item.set_aside)}</dd>
        </div>
        <div>
          <dt>Projected contributions</dt>
          <dd>{fmt(item.projected_contributions)}</dd>
        </div>
        <div>
          <dt>Projected by deadline</dt>
          <dd>{fmt(item.projected_funding)}</dd>
        </div>
      </dl>
      {item.funding_gap != null && (
        <p className={item.funding_gap > 0 ? 'notice danger' : 'notice'}>
          {item.funding_gap > 0
            ? `${fmt(item.funding_gap)} additional funding needed by ${dateLabel(item.target_date)}`
            : 'On track with budgeted contributions'}
        </p>
      )}
    </div>
  );
}

export function PlanningOverview({
  currency,
  revision,
  month,
  onOpen,
  onChanged,
}: {
  currency: string;
  revision: number;
  month: string;
  onOpen: () => void;
  onChanged: () => void;
}) {
  const [result, setResult] = useState<{
    month: string;
    data: PlanningData;
  } | null>(null);
  const data = result?.month === month ? result.data : null;
  const [error, setError] = useState<{ month: string; message: string } | null>(
    null,
  );
  useEffect(() => {
    let active = true;
    api<PlanningData>(`/planning?month=${month}`)
      .then((value) => {
        if (active) {
          setResult({ month, data: value });
          setError(null);
        }
      })
      .catch((e) => {
        if (active) setError({ month, message: e.message });
      });
    return () => {
      active = false;
    };
  }, [revision, month]);
  if (error?.month === month)
    return (
      <p role="alert" className="notice danger">
        Funding coverage unavailable: {error.message}
      </p>
    );
  if (!data) return null;
  const annual = data.plans.filter((p) => p.monthly_allocation !== undefined);
  const point = data.projection?.months.find((p) => p.month === month);
  return (
    <details
      className="panel planning-overview"
      open={annual.some((p) => (p.funding_gap ?? 0) > 0) || undefined}
    >
      <summary>Annual expense funding & Planning</summary>
      <div className="section-head">
        <p>
          {data.plans.length} plans · {money(data.total_planned, currency)}{' '}
          planned ·{' '}
          {data.set_aside === null
            ? 'Set savings to track funding'
            : money(data.set_aside, currency) + ' set aside'}
        </p>
        <button className="secondary small" onClick={onOpen}>
          Open Planning
        </button>
      </div>
      {annual.map((item) => (
        <article key={item.id} className="plan-card">
          <h3>
            {item.name} · {money(item.amount, currency)} due{' '}
            {dateLabel(item.target_date)}
          </h3>
          <AnnualFunding item={item} currency={currency} />
        </article>
      ))}
      {!annual.length && (
        <p>
          Track annual bills in Planning to see their funding coverage and
          upcoming shortfalls.
        </p>
      )}
      {point?.balance != null && (
        <p className={point.balance < data.floor ? 'notice danger' : 'notice'}>
          Projected end-of-month cash: {money(point.balance, currency)}
          {!data.projection?.income_complete
            ? ' · incomplete income forecast'
            : ''}
          .
        </p>
      )}
      <p className="planning-note">
        Assumes future contributions arrive before payment and are not already
        in your recorded balance. Other categories are not reassigned.
      </p>
      <details>
        <summary>Update actual savings</summary>
        <SavingsSettings currency={currency} onChanged={onChanged} />
      </details>
    </details>
  );
}
