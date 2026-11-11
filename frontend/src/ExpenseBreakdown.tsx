import { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ReferenceLine,
} from 'recharts';
import {
  CalendarRange,
  ChevronRight,
  ArrowLeft,
  LoaderCircle,
  Minus,
  Plus,
} from 'lucide-react';
import { api, money, monthLabel, shiftMonth } from './api';

type Entry = {
  id: string;
  record_id: string;
  date: string | null;
  month: string;
  description: string;
  category_id: string | null;
  category_name: string;
  kind: string;
  amount: number;
  signed_amount: number;
  account_name: string | null;
};
type CategoryTotal = {
  category_id: string | null;
  name: string;
  charges: number;
  refunds: number;
  net: number;
  entry_count: number;
};
type Breakdown = {
  start: string;
  end: string;
  basis: 'actual' | 'forecast';
  charges: number;
  refunds: number;
  net: number;
  entry_count: number;
  categories: CategoryTotal[];
  entries: Entry[];
  months: { month: string; status: string; partial_range: boolean }[];
};
const colors = [
  '#548574',
  '#b6844d',
  '#7d76a3',
  '#6693ad',
  '#bd7478',
  '#8c9859',
  '#8a8d96',
];
function lastDay(month: string) {
  const [y, m] = month.split('-').map(Number);
  return `${month}-${new Date(y, m, 0).getDate()}`;
}
function shortDate(value: string) {
  return new Date(value + 'T12:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function ExpenseBreakdown({
  month,
  actualMonth,
  currentActual,
  onCurrentActualChange,
  onMonthChange,
  currency,
  revision,
  view = 'breakdown',
  active = true,
  onShowEntries,
  onShowBreakdown,
}: {
  month: string;
  actualMonth: string;
  currentActual: boolean;
  onCurrentActualChange: (checked: boolean) => void;
  onMonthChange: (month: string, basis: 'actual' | 'forecast') => void;
  currency: string;
  revision: number;
  onShowBreakdown?: () => void;
  view?: 'breakdown' | 'entries';
  active?: boolean;
  onShowEntries?: () => void;
}) {
  const [basis, setBasis] = useState<'actual' | 'forecast'>('actual');
  const rangeMonth = basis === 'actual' ? actualMonth : month;
  const [start, setStart] = useState(actualMonth + '-01');
  const [end, setEnd] = useState(lastDay(actualMonth));
  const [data, setData] = useState<Breakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [focus, setFocus] = useState<string | null | undefined>(undefined);
  const [limit, setLimit] = useState(50);
  const [monthDraft, setMonthDraft] = useState(actualMonth);
  const [monthError, setMonthError] = useState('');
  useEffect(() => {
    setStart(rangeMonth + '-01');
    setEnd(lastDay(rangeMonth));
    setFocus(undefined);
  }, [rangeMonth]);
  useEffect(() => {
    setFocus(undefined);
    setLimit(50);
  }, [start, end, basis]);
  useEffect(() => {
    if (!active) return;
    let current = true;
    const controller = new AbortController();
    setError('');
    if (!start || !end || start > end) {
      setLoading(false);
      setError(
        'Choose a valid start and end, with the end on or after the start.',
      );
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ start, end, basis });
    api<Breakdown>(
      '/expenses/breakdown?' + params,
      'GET',
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (current) setData(value);
      })
      .catch((e) => {
        if (current && (e as Error).name !== 'AbortError')
          setError((e as Error).message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [start, end, basis, revision, active]);
  const currentData =
    !!data && data.start === start && data.end === end && data.basis === basis;
  const fmt = (n: number) => money(n, currency);
  const selected = data?.categories.find((c) => c.category_id === focus);
  const entries =
    data?.entries.filter(
      (entry) => focus === undefined || entry.category_id === focus,
    ) ?? [];
  const total = focus === undefined ? (data?.net ?? 0) : (selected?.net ?? 0);
  const selectCategory = (id: string | null) => {
    setFocus(id);
    setLimit(50);
    onShowEntries?.();
  };
  const changeBasis = (value: 'actual' | 'forecast') => {
    if (value === 'forecast') {
      setStart((start.slice(0, 7) || month) + '-01');
      setEnd(lastDay(end.slice(0, 7) || month));
    }
    setBasis(value);
  };
  const navigationMonth = start.slice(0, 7) || rangeMonth;
  const goMonth = (value: string) => {
    setMonthDraft(value);
    setMonthError('');
    setStart(value + '-01');
    setEnd(lastDay(value));
    setFocus(undefined);
    onMonthChange(value, basis);
  };
  useEffect(() => {
    setMonthDraft(navigationMonth);
    setMonthError('');
  }, [navigationMonth]);
  const validMonth = (value: string) =>
    /^\d{4}-(0[1-9]|1[0-2])$/.test(value) &&
    value >= '1900-01' &&
    value <= '9998-12';
  const applyMonth = () => {
    if (!validMonth(monthDraft)) {
      setMonthError(
        'Enter a month from 1900-01 through 9998-12 using YYYY-MM.',
      );
      return;
    }
    setMonthError('');
    if (monthDraft !== navigationMonth) goMonth(monthDraft);
  };
  const stepMonth = (offset: number) => {
    const next = shiftMonth(
      validMonth(monthDraft) ? monthDraft : navigationMonth,
      offset,
    );
    if (validMonth(next)) goMonth(next);
  };
  return (
    <section className="panel expense-breakdown" id="expense-breakdown">
      <div className="section-head">
        <div>
          <h2>
            {view === 'entries' ? 'All expense entries' : 'Expense breakdown'}
          </h2>
          <p>
            {basis === 'actual'
              ? start && end
                ? `See exactly where your money went · ${shortDate(start)} – ${shortDate(end)}.`
                : 'Choose a date range.'
              : 'See the bills and included purchases in your plan.'}
          </p>
        </div>
        <div className="breakdown-heading-controls">
          {basis === 'actual' && (
            <label
              className="checkbox"
              title="Checked uses the selected budget month; unchecked uses its previous month"
            >
              <input
                type="checkbox"
                checked={currentActual}
                onChange={(e) => onCurrentActualChange(e.target.checked)}
              />
              Current month
            </label>
          )}
          <label className="breakdown-basis">
            <span className="sr-only">Expense source</span>
            <select
              value={basis}
              onChange={(e) =>
                changeBasis(e.target.value as 'actual' | 'forecast')
              }
            >
              <option value="actual">Actual spending</option>
              <option value="forecast">Planned expenses</option>
            </select>
          </label>
        </div>
      </div>
      <div className="breakdown-month-nav">
        <div
          className="month-stepper"
          role="group"
          aria-label="Expense breakdown month"
        >
          <button
            className="icon"
            aria-label="Previous breakdown month"
            disabled={navigationMonth <= '1900-01'}
            onClick={() => stepMonth(-1)}
          >
            <Minus size={17} />
          </button>
          <label>
            <span className="sr-only">Breakdown month</span>
            <input
              type="text"
              aria-label="Breakdown month"
              placeholder="YYYY-MM"
              maxLength={7}
              autoComplete="off"
              spellCheck={false}
              value={monthDraft}
              aria-invalid={!!monthError}
              aria-describedby={
                monthError
                  ? 'breakdown-month-format breakdown-month-error'
                  : 'breakdown-month-format'
              }
              onChange={(e) => setMonthDraft(e.target.value)}
              onBlur={applyMonth}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  applyMonth();
                }
                if (e.key === 'Escape') {
                  setMonthDraft(navigationMonth);
                  setMonthError('');
                }
              }}
            />
            <small id="breakdown-month-format">
              YYYY-MM · Enter or leave the field to apply
            </small>
          </label>
          <button
            className="icon"
            aria-label="Next breakdown month"
            disabled={navigationMonth >= '9998-12'}
            onClick={() => stepMonth(1)}
          >
            <Plus size={17} />
          </button>
        </div>
        <span>
          Type a month, use ± to step through full months, or choose a custom
          range below.
        </span>
      </div>
      {monthError && (
        <p className="notice danger" id="breakdown-month-error" role="alert">
          {monthError}
        </p>
      )}
      <div className="breakdown-controls">
        <CalendarRange size={18} />
        <label>
          From
          <input
            aria-label="Breakdown start"
            type={basis === 'actual' ? 'date' : 'month'}
            value={basis === 'actual' ? start : start.slice(0, 7)}
            onChange={(e) =>
              setStart(
                basis === 'actual'
                  ? e.target.value
                  : e.target.value
                    ? e.target.value + '-01'
                    : '',
              )
            }
          />
        </label>
        <label>
          Through
          <input
            aria-label="Breakdown end"
            type={basis === 'actual' ? 'date' : 'month'}
            value={basis === 'actual' ? end : end.slice(0, 7)}
            onChange={(e) =>
              setEnd(
                basis === 'actual'
                  ? e.target.value
                  : e.target.value
                    ? lastDay(e.target.value)
                    : '',
              )
            }
          />
        </label>
        <button
          className="secondary small"
          onClick={() => {
            setStart(rangeMonth + '-01');
            setEnd(lastDay(rangeMonth));
            setFocus(undefined);
          }}
        >
          Reset to selected month
        </button>
      </div>
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
      {loading && !currentData && (
        <div className="breakdown-loading" role="status">
          <LoaderCircle size={18} className="spin" />
          Loading expense details…
        </div>
      )}
      {active && data && currentData && (
        <>
          <div className="breakdown-totals">
            <div>
              <span>
                {basis === 'actual' ? 'Purchases & fees' : 'Planned expenses'}
              </span>
              <strong>{fmt(data.charges)}</strong>
            </div>
            <div>
              <span>Refunds</span>
              <strong className="green">{fmt(data.refunds)}</strong>
            </div>
            <div>
              <span>Net expenses</span>
              <strong>{fmt(data.net)}</strong>
            </div>
            <div>
              <span>
                {basis === 'actual' ? 'Transactions' : 'Planned entries'}
              </span>
              <strong>{data.entry_count}</strong>
            </div>
          </div>
          {basis === 'actual' &&
            data.months.some((m) => m.status !== 'complete') && (
              <p className="breakdown-note">
                Recorded spending only.{' '}
                {data.months
                  .filter((m) => m.status !== 'complete')
                  .map((m) => `${monthLabel(m.month, true)}: ${m.status}`)
                  .join(' · ')}
                .
              </p>
            )}
          {!data.categories.length ? (
            <div className="empty">
              <h3>
                {basis === 'actual'
                  ? 'No recorded expenses in this range'
                  : 'No planned expenses in these months'}
              </h3>
              <p>
                {basis === 'actual'
                  ? 'Import a statement, record a transaction, or try another range. Empty records do not establish zero spending.'
                  : 'Add recurring bills or include a purchase estimate to see the breakdown.'}
              </p>
            </div>
          ) : (
            <>
              {view === 'breakdown' && (
                <>
                  <div className="breakdown-grid">
                    <div
                      className="breakdown-chart"
                      style={{
                        height: Math.max(220, data.categories.length * 43 + 45),
                      }}
                      aria-label="Net expenses by category; use the category buttons or table to drill down"
                    >
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={data.categories}
                          layout="vertical"
                          margin={{ left: 0, right: 30, top: 8, bottom: 10 }}
                        >
                          <CartesianGrid
                            horizontal={false}
                            stroke="#e7ece1"
                            strokeDasharray="3 5"
                          />
                          <XAxis
                            type="number"
                            tickFormatter={(n) => fmt(Number(n))}
                            tick={{ fontSize: 10, fill: '#84917a' }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <YAxis
                            type="category"
                            dataKey="name"
                            tickFormatter={(value: string) =>
                              value.length > 18
                                ? value.slice(0, 17) + '…'
                                : value
                            }
                            width={110}
                            tick={{ fontSize: 11, fill: '#637957' }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <ReferenceLine x={0} stroke="#cfd9c5" />
                          <Tooltip formatter={(value) => fmt(Number(value))} />
                          <Bar
                            name="Net expenses"
                            dataKey="net"
                            radius={[0, 4, 4, 0]}
                            maxBarSize={20}
                            onClick={(_, index) =>
                              selectCategory(data.categories[index].category_id)
                            }
                          >
                            {data.categories.map((c, i) => (
                              <Cell
                                key={c.category_id ?? 'uncategorized'}
                                fill={colors[i % colors.length]}
                                opacity={
                                  focus === undefined || focus === c.category_id
                                    ? 1
                                    : 0.35
                                }
                                cursor="pointer"
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="category-breakdown-list">
                      {data.categories.map((c, i) => (
                        <button
                          className={
                            'category-breakdown-row ' +
                            (focus === c.category_id ? 'selected' : '')
                          }
                          key={c.category_id ?? 'uncategorized'}
                          onClick={() => selectCategory(c.category_id)}
                          aria-pressed={focus === c.category_id}
                        >
                          <i
                            style={{ background: colors[i % colors.length] }}
                          />
                          <span className="grow">
                            <strong>{c.name}</strong>
                            <small>
                              {c.entry_count}{' '}
                              {basis === 'actual'
                                ? 'transactions'
                                : 'planned entries'}
                            </small>
                          </span>
                          <strong>{fmt(c.net)}</strong>
                          <ChevronRight size={15} />
                        </button>
                      ))}
                    </div>
                  </div>
                  <details className="breakdown-category-table">
                    <summary>Category totals as a table</summary>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Category</th>
                            <th>Charges</th>
                            <th>Refunds</th>
                            <th>Net expenses</th>
                            <th>Entries</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.categories.map((c) => (
                            <tr key={c.category_id ?? 'uncategorized'}>
                              <th>
                                <button
                                  className="text-button"
                                  onClick={() => selectCategory(c.category_id)}
                                >
                                  {c.name}
                                </button>
                              </th>
                              <td>{fmt(c.charges)}</td>
                              <td>{fmt(c.refunds)}</td>
                              <td>{fmt(c.net)}</td>
                              <td>{c.entry_count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </>
              )}
              {view === 'entries' && (
                <>
                  <div className="breakdown-detail-head">
                    <div>
                      <h3>
                        {focus === undefined
                          ? 'Entries in this range'
                          : (selected?.name ?? 'Selected category')}
                      </h3>
                      <p>
                        {shortDate(data.start)} – {shortDate(data.end)} ·{' '}
                        {entries.length} entries · {fmt(total)} net
                      </p>
                    </div>
                    {focus !== undefined && (
                      <button
                        className="text-button"
                        onClick={() => {
                          setFocus(undefined);
                          setLimit(50);
                          onShowBreakdown?.();
                        }}
                      >
                        <ArrowLeft size={14} />
                        All categories
                      </button>
                    )}
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>{basis === 'actual' ? 'Date' : 'Month'}</th>
                          <th>Expense</th>
                          <th>Category</th>
                          <th>Type</th>
                          {basis === 'actual' && <th>Card account</th>}
                          <th>Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {entries.slice(0, limit).map((entry) => (
                          <tr key={entry.id}>
                            <td>
                              {entry.date ?? monthLabel(entry.month, true)}
                            </td>
                            <td>
                              <strong>{entry.description}</strong>
                            </td>
                            <td>{entry.category_name}</td>
                            <td>{entry.kind.replaceAll('_', ' ')}</td>
                            {basis === 'actual' && (
                              <td>{entry.account_name ?? '—'}</td>
                            )}
                            <td
                              className={entry.signed_amount < 0 ? 'green' : ''}
                            >
                              {fmt(entry.signed_amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {entries.length > limit && (
                    <div className="breakdown-more">
                      <button
                        className="secondary small"
                        onClick={() => setLimit((n) => n + 50)}
                      >
                        Show more ({entries.length - limit} remaining)
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
          <div className="panel-foot">
            {basis === 'actual'
              ? 'Date range includes both end dates. Refunds reduce spending; card payments and transfers are excluded.'
              : 'Full calendar months. Annual bills follow their distribution setting; draft purchases and income are excluded. Actual spending is separate.'}
          </div>
        </>
      )}
    </section>
  );
}
