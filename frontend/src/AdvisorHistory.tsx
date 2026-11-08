import { money, monthLabel } from './api';
import type { AdvisorSpendingHistory } from './api';

export default function AdvisorHistory({
  history,
  currency,
}: {
  history: AdvisorSpendingHistory;
  currency: string;
}) {
  const fmt = (n: number | null) =>
    n === null ? 'Unknown' : money(n, currency);
  const renderRows = (
    rows: AdvisorSpendingHistory['categories'],
    payees = false,
  ) => (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label={
        payees
          ? 'Local payee spending history'
          : 'Local category spending history'
      }
    >
      <table>
        <caption>
          {payees ? 'Selected normalized payees' : 'Categories'} · recorded net
          spending, {history.start_month} through {history.end_month}
        </caption>
        <thead>
          <tr>
            <th>{payees ? 'Payee · category' : 'Category'}</th>
            {history.months.map((month) => (
              <th key={month.month}>
                {monthLabel(month.month, true)}
                <small>{month.status}</small>
              </th>
            ))}
            <th>2-month change</th>
            <th>3-month change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <th>
                {'payee' in row ? String(row.payee) + ' · ' : ''}
                {row.category}
              </th>
              {row.monthly_net_minor.map((n, j) => (
                <td key={j}>{n === null ? 'Missing' : fmt(n)}</td>
              ))}
              {[2, 3].map((count) => {
                const comparison = row.comparisons.find(
                  (c) => c.months === count,
                );
                return (
                  <td key={count}>
                    {comparison ? fmt(comparison.change_minor) : 'Unavailable'}
                    {comparison && (
                      <small>
                        {comparison.from_month} → {comparison.to_month}
                        {comparison.partial_month_count > 0
                          ? ' · incomplete data'
                          : ''}
                        {comparison.missing_month_count > 0
                          ? ' · missing data'
                          : ''}
                      </small>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <details className="advisor-history">
      <summary>Local transaction history used for this answer</summary>
      <p>
        Read-only local context. Refunds reduce spending; card payments and
        transfers are excluded. Current and future months are excluded from
        comparisons. Missing months are unknown; incomplete months may
        understate spending. Changes compare the first and last month of each
        window.
      </p>
      {renderRows(history.categories)}
      <details>
        <summary>
          Selected payees ({history.payees.length}
          {history.additional_payees_omitted
            ? `, ${history.additional_payees_omitted} others omitted`
            : ''}
          )
        </summary>
        <p>{history.payee_selection}</p>
        {renderRows(history.payees, true)}
      </details>
      <p>
        This context is sent only to your local model. It is never included in
        Brave search requests.
      </p>
    </details>
  );
}
