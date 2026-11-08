import { money, monthLabel } from './api';

export type SpendingComparison = {
  previous_month: string;
  month: string;
  previous_status: string;
  current_status: string;
  totals: SpendingChange;
  accounts: SpendingChange[];
  categories: SpendingChange[];
  budget_impact?: {
    month: string;
    planned_income_minor: number | null;
    actual_spending_minor: number | null;
    room_after_recorded_spending_minor: number | null;
  }[];
};
type SpendingChange = {
  name: string;
  previous_minor: number | null;
  current_minor: number | null;
  change_minor: number | null;
};

export default function AdvisorComparison({
  comparison,
  currency,
}: {
  comparison: SpendingComparison;
  currency: string;
}) {
  const fmt = (value: number | null) =>
    value === null ? 'Unknown' : money(value, currency);
  const rows = (values: SpendingChange[], label: string) => (
    <div className="table-scroll" tabIndex={0} role="region" aria-label={label}>
      <table>
        <caption>{label}</caption>
        <thead>
          <tr>
            <th>Recorded spending</th>
            <th>{monthLabel(comparison.previous_month, true)}</th>
            <th>{monthLabel(comparison.month, true)}</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {values.map((row) => (
            <tr key={row.name}>
              <th>{row.name}</th>
              <td>{fmt(row.previous_minor)}</td>
              <td>{fmt(row.current_minor)}</td>
              <td>
                {row.change_minor !== null && row.change_minor > 0 ? '+' : ''}
                {fmt(row.change_minor)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <>
      <section className="panel">
        <div className="section-head">
          <div>
            <h2>What changed this month?</h2>
            <p>
              {monthLabel(comparison.previous_month, true)} →{' '}
              {monthLabel(comparison.month, true)} · recorded transactions
            </p>
          </div>
        </div>
        <div className="advisor-context">
          <p>
            Latest two finished months through the selected month. Purchases and
            fees minus refunds, grouped by transaction date. Card payments and
            transfers are excluded.
          </p>
          {(comparison.previous_status !== 'complete' ||
            comparison.current_status !== 'complete') && (
            <p className="notice" role="status">
              {monthLabel(comparison.previous_month)}:{' '}
              {comparison.previous_status}. {monthLabel(comparison.month)}:{' '}
              {comparison.current_status}. Incomplete imports can understate
              spending; missing months are unknown.
            </p>
          )}
          {rows(
            [comparison.totals, ...comparison.accounts],
            'By bank or card account',
          )}
          <details>
            <summary>Category changes</summary>
            {rows(comparison.categories, 'By category')}
          </details>
          <p>
            These are recorded charges and debits, not forecast allowances,
            statement balances, or proof of why spending changed.
          </p>
        </div>
      </section>
      {comparison.budget_impact && (
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Calculated budget impact</h2>
              <p>
                Planned income less recorded spending · same two finished months
              </p>
            </div>
          </div>
          <div className="advisor-context">
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Budget impact from recorded spending"
            >
              <table>
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Planned income</th>
                    <th>Recorded spending</th>
                    <th>Room after recorded spending</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.budget_impact.map((row) => (
                    <tr key={row.month}>
                      <th>{monthLabel(row.month, true)}</th>
                      <td>{fmt(row.planned_income_minor)}</td>
                      <td>{fmt(row.actual_spending_minor)}</td>
                      <td>{fmt(row.room_after_recorded_spending_minor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Uses actual charges and debits instead of forecast expense
              allowances. Income is your plan, not verified deposits. Incomplete
              spending can overstate room; this is not a bank balance or an
              achieved savings increase.
            </p>
          </div>
        </section>
      )}
    </>
  );
}
