import { useEffect, useId, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  Trash2,
} from 'lucide-react';
import { api, inputAmount, money, nonnegativeMinor } from './api';
import type { ReserveCheck, SavingsSnapshot } from './api';

const dateLabel = (value: string) =>
  new Date(value + 'T12:00:00').toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

export default function ReserveMonitor({
  currency,
  revision,
  manage = false,
  collapsible = false,
  onConfigure,
  onChanged,
}: {
  currency: string;
  revision: number;
  manage?: boolean;
  collapsible?: boolean;
  onConfigure: () => void;
  onChanged: () => void;
}) {
  const [report, setReport] = useState<ReserveCheck | null>(null);
  const [baseline, setBaseline] = useState('');
  const [month, setMonth] = useState('');
  const [balance, setBalance] = useState('');
  const [asOf, setAsOf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showPlan, setShowPlan] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const read = () => {
      if (document.visibilityState === 'hidden') return;
      api<ReserveCheck>('/reserve-check', 'GET', undefined, controller.signal)
        .then((value) => {
          if (active) setReport(value);
        })
        .catch((e) => {
          if (active && e.name !== 'AbortError') setError(e.message);
        });
    };
    read();
    const timer = setInterval(read, 60000);
    window.addEventListener('focus', read);
    document.addEventListener('visibilitychange', read);
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
      window.removeEventListener('focus', read);
      document.removeEventListener('visibilitychange', read);
    };
  }, [revision]);
  useEffect(() => {
    if (!manage || initialized || !report) return;
    let active = true;
    api<SavingsSnapshot>('/savings')
      .then((saved) => {
        if (!active) return;
        setBaseline(
          report.plan
            ? inputAmount(report.plan.amount, currency)
            : saved.amount === null
              ? ''
              : inputAmount(saved.amount, currency),
        );
        setMonth(report.plan?.start_date.slice(0, 7) ?? saved.month);
        setAsOf(report.today);
        setInitialized(true);
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [manage, report, initialized, currency]);
  const fmt = (amount: number) => money(amount, currency);
  const run = async (action: () => Promise<ReserveCheck>) => {
    setBusy(true);
    setError('');
    try {
      setReport(await action());
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const savePlan = () => {
    if (
      report?.plan &&
      !window.confirm(
        'Replace the saved funding target using these inputs and the current annual schedules? Recording a balance alone does not require this.',
      )
    )
      return;
    void run(() =>
      api<ReserveCheck>('/reserve-check/plan', 'PUT', {
        amount: nonnegativeMinor(baseline, currency),
        month,
      }),
    );
  };
  const record = () =>
    void run(() =>
      api<ReserveCheck>('/reserve-check/balances', 'POST', {
        amount: nonnegativeMinor(balance, currency),
        as_of: asOf,
      }),
    );
  const deletePlan = () => {
    if (
      !window.confirm(
        'Permanently delete this reserve plan and its saved funding target? Annual bills, savings balances, and transactions will remain. This cannot be undone.',
      )
    )
      return;
    void run(async () => {
      const updated = await api<ReserveCheck>('/reserve-check/plan', 'DELETE');
      setShowPlan(false);
      setInitialized(false);
      return updated;
    });
  };
  if (!report)
    return error ? (
      <p className="notice danger" role="alert">
        Reserve check unavailable: {error}
      </p>
    ) : manage ? (
      <p className="notice">Loading reserve plan…</p>
    ) : null;
  if (!manage && (!report.enabled || report.status === 'no_bills')) return null;
  const warning = ['needs_update', 'below_target', 'payment_risk'].includes(
    report.status,
  );
  const message =
    report.status === 'not_configured'
      ? 'Set up a funding target for your dated annual bills.'
      : report.dismissed
        ? `Reserve alerts dismissed until ${dateLabel(report.plan!.dismissed_until!)}.`
        : report.status === 'needs_update'
          ? `Update your savings balance to check your annual-bill funding${report.checkpoint ? ' for ' + dateLabel(report.checkpoint) : ''}.`
          : report.status === 'below_target'
            ? `Savings is ${fmt(report.shortfall!)} below your planned annual-bill reserve.`
            : report.status === 'payment_risk'
              ? 'An upcoming annual payment may be underfunded.'
              : report.status === 'scheduled'
                ? `Next reserve checkpoint: ${dateLabel(report.next_checkpoint!)}.`
                : 'Annual bill reserve is on track.';
  const details = (
    <>
      <p className="reserve-explanation">
        The target includes planned annual-bill allocations and excludes
        optional monthly surplus. It treats the starting balance as available
        for these bills. Transfers are planned, not verified. Payments are
        assumed on their due dates; no payment is confirmed here.
      </p>
      {report.plan && (
        <>
          <p>
            Fixed baseline: <strong>{fmt(report.plan.amount)}</strong> ·{' '}
            {dateLabel(report.plan.start_date)}. Balance updates do not reset
            it.
          </p>
          <p>
            Target = baseline + allocations due by the checkpoint − annual
            payments scheduled before that date. Targets stop at zero after a
            funding shortfall; upcoming payment checks also consider available
            funds.
          </p>
          <div className="table-scroll">
            <table>
              <caption>
                Annual-bill funding plan · current and upcoming checkpoints
              </caption>
              <thead>
                <tr>
                  <th>Checkpoint</th>
                  <th>New allocation due</th>
                  <th>Allocations to date</th>
                  <th>Payments before checkpoint</th>
                  <th>Reserve target</th>
                </tr>
              </thead>
              <tbody>
                {report.checkpoints?.map((row) => (
                  <tr key={row.date}>
                    <th>{dateLabel(row.date)}</th>
                    <td>
                      {fmt(row.allocation)}
                      {row.allocations.map((a, i) => (
                        <small key={i}>
                          {a.name}: {fmt(a.amount)}
                        </small>
                      ))}
                    </td>
                    <td>{fmt(row.allocations_to_date)}</td>
                    <td>{fmt(row.payments_to_date)}</td>
                    <td>{fmt(row.target)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            This is a reserve target, not an additional forecast expense.
            Undated annual allowances and annual bills without monthly
            distribution are outside this reserve plan. Full income and expense
            projections remain in Purchase planner.
          </p>
        </>
      )}
    </>
  );
  return (
    <section
      className={
        'panel reserve-monitor ' +
        (!manage && warning && !report.dismissed ? 'reserve-warning' : '')
      }
    >
      <div className="section-head">
        <div>
          <h2>{manage ? 'Annual bill reserve plan' : 'Annual bill reserve'}</h2>
          <p
            role={!manage && warning && !report.dismissed ? 'alert' : undefined}
          >
            {manage
              ? 'Keep a fixed funding target and check it against manually recorded balances.'
              : message}
          </p>
        </div>
        <div className="button-group reserve-header-actions">
          {report.status === 'on_track' ? (
            <Check size={19} />
          ) : warning && !report.dismissed ? (
            <AlertTriangle size={19} />
          ) : (
            <CalendarClock size={19} />
          )}
          {collapsible && (
            <button
              className="text-button"
              aria-expanded={expanded}
              aria-controls={contentId}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              {expanded ? 'Hide reserve details' : 'Show reserve details'}
            </button>
          )}
        </div>
      </div>
      <div
        id={contentId}
        className="reserve-content"
        hidden={collapsible && !expanded}
      >
        {manage && !report.enabled && (
          <p className="notice">
            Reserve alerts are turned off in Settings. You can still manage the
            plan and recorded balances here.
          </p>
        )}
        {report.plan?.schedule_changed && (
          <p className="notice">
            Annual schedules changed since this target was saved. Review and
            explicitly replace the funding target to use those changes.
          </p>
        )}
        {report.plan && (
          <div className="reserve-summary">
            <div>
              <span>Target · {dateLabel(report.target_as_of!)}</span>
              <strong>{fmt(report.target!)}</strong>
            </div>
            <div>
              <span>
                Last manual balance
                {report.latest ? ' · ' + dateLabel(report.latest.as_of) : ''}
              </span>
              <strong>
                {report.latest ? fmt(report.latest.amount) : 'Not recorded'}
              </strong>
              {!report.fresh && (
                <small>Balance needs updating for this checkpoint.</small>
              )}
            </div>
            <div>
              <span>Next target · {dateLabel(report.next_checkpoint!)}</span>
              <strong>{fmt(report.next_target!)}</strong>
            </div>
          </div>
        )}
        {!report.dismissed &&
          report.upcoming?.map((payment) => (
            <div
              className={'notice ' + (payment.shortfall ? 'danger' : '')}
              key={payment.due_date}
            >
              <div>
                <strong>
                  {payment.bills.map((b) => b.name).join(' + ')} ·{' '}
                  {fmt(payment.amount)} · due {dateLabel(payment.due_date)}
                </strong>
                <p>
                  {payment.projected_before_payment === null
                    ? 'Record a balance to check payment coverage.'
                    : `Projected reserve before payment: ${fmt(payment.projected_before_payment)}.${payment.shortfall ? ' Potential shortfall: ' + fmt(payment.shortfall) + '.' : ''}`}{' '}
                  {payment.assumes_future_allocations
                    ? 'Includes future planned allocations; confirm they will arrive in time.'
                    : 'Uses the last manual balance and scheduled payments.'}{' '}
                  {!report.fresh
                    ? 'The balance is unconfirmed for this checkpoint.'
                    : ''}
                </p>
              </div>
            </div>
          ))}
        {error && (
          <p className="notice danger" role="alert">
            {error}
          </p>
        )}
        {!manage ? (
          <>
            <div className="button-group">
              <button className="secondary small" onClick={onConfigure}>
                {report.plan ? 'Update savings' : 'Set up reserve plan'}
              </button>
              {report.plan && (
                <button
                  className="text-button"
                  aria-expanded={showPlan}
                  onClick={() => setShowPlan(!showPlan)}
                >
                  {showPlan ? 'Hide funding plan' : 'View funding plan'}
                </button>
              )}
              {warning && !report.dismissed && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      api<ReserveCheck>('/reserve-check/dismiss', 'POST'),
                    )
                  }
                >
                  Dismiss until next checkpoint
                </button>
              )}
            </div>
            {showPlan && <div className="reserve-details">{details}</div>}
          </>
        ) : (
          <>
            {report.plan && (
              <div className="button-group">
                <button
                  type="button"
                  className="text-button red"
                  disabled={busy}
                  onClick={deletePlan}
                >
                  <Trash2 size={14} /> Permanently delete reserve plan
                </button>
              </div>
            )}
            {report.eligible_bill_count === 0 && (
              <p className="notice">
                Configure an annual payable with monthly distribution and a due
                month/day to use reserve targets.
              </p>
            )}
            <form
              className="reserve-form"
              onSubmit={(e) => {
                e.preventDefault();
                record();
              }}
            >
              <h3>Record savings balance</h3>
              <p>
                A manual opening balance on the selected date, before annual
                payments due that day. Record an after-payment balance on the
                following date. This checks reserve progress without changing
                the funding target or the Purchase planner snapshot.
              </p>
              <div className="form-grid">
                <label>
                  Recorded savings ({currency})
                  <input
                    aria-label="Recorded savings amount"
                    type="number"
                    min="0"
                    step={currency === 'JPY' ? 1 : 0.01}
                    required
                    value={balance}
                    disabled={busy || !initialized}
                    onChange={(e) => setBalance(e.target.value)}
                  />
                </label>
                <label>
                  Balance as of
                  <input
                    aria-label="Recorded savings date"
                    type="date"
                    required
                    value={asOf}
                    max={report.today}
                    disabled={busy || !initialized}
                    onChange={(e) => setAsOf(e.target.value)}
                  />
                </label>
              </div>
              <button disabled={busy || !initialized || !balance || !asOf}>
                Record balance
              </button>
            </form>
            <details className="reserve-details">
              <summary>
                {report.plan
                  ? 'Review or replace funding target'
                  : 'Set funding target'}
              </summary>
              <form
                className="reserve-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  savePlan();
                }}
              >
                <p>
                  Use an opening balance for the baseline month. This explicitly
                  saves the current dated annual schedules. Future balance
                  entries leave this target unchanged.
                </p>
                <div className="form-grid">
                  <label>
                    Reserve baseline ({currency})
                    <input
                      aria-label="Reserve baseline amount"
                      type="number"
                      min="0"
                      step={currency === 'JPY' ? 1 : 0.01}
                      required
                      value={baseline}
                      disabled={busy || !initialized}
                      onChange={(e) => setBaseline(e.target.value)}
                    />
                  </label>
                  <label>
                    Reserve baseline month
                    <input
                      aria-label="Reserve baseline month"
                      type="month"
                      required
                      value={month}
                      max={report.today.slice(0, 7)}
                      disabled={busy || !initialized}
                      onChange={(e) => setMonth(e.target.value)}
                    />
                  </label>
                </div>
                <button
                  disabled={
                    busy ||
                    !initialized ||
                    !baseline ||
                    !month ||
                    !report.eligible_bill_count
                  }
                >
                  {report.plan
                    ? 'Replace funding target'
                    : 'Start reserve plan'}
                </button>
              </form>
              {details}
            </details>
            <details className="reserve-details">
              <summary>Recorded balance history</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>As of</th>
                      <th>Savings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.observations.map((row) => (
                      <tr key={row.as_of}>
                        <th>{dateLabel(row.as_of)}</th>
                        <td>{fmt(row.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                Recording the same date corrects its balance. No transactions or
                payments are created.
              </p>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
