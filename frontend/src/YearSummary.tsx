import { useState, useEffect } from 'react';
import { api, monthLabel, money } from './api';
import type { SavingsAwareForecast } from './api';
export default function YearSummary({
  year,
  currency,
  revision,
  selectMonth,
}: {
  year: string;
  currency: string;
  revision: number;
  selectMonth: (m: string) => void;
}) {
  const [result, setResult] = useState<{
    year: string;
    data: SavingsAwareForecast[];
  }>({ year, data: [] });
  const data = result.year === year ? result.data : [];
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api<SavingsAwareForecast[]>(
      `/forecasts?start=${year}-01&months=12&include_savings=true`,
    )
      .then((d) => {
        if (active) {
          setResult({ year, data: d });
          setError('');
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [year, revision]);
  const fmt = (n: number | null | undefined) =>
    n == null ? 'Not projected' : money(n, currency);
  const max = Math.max(1, ...data.flatMap((d) => [d.income, d.expenses]));
  return (
    <>
      {error && (
        <p role="alert" className="notice danger">
          {error}
        </p>
      )}
      <div className="year-chart">
        {data.map((d) => (
          <button
            key={d.month}
            className={
              'year-month ' +
              (d.savings_adjusted_deficit || (d.funding_gap ?? 0) > 0
                ? 'over'
                : '')
            }
            aria-label={`${monthLabel(d.month)}: income ${money(d.income, currency)}, expenses ${money(d.expenses, currency)}; projected cash ${fmt(d.remaining_with_savings)}${d.savings_adjusted_deficit ? (d.remaining_with_savings === null ? ', monthly budget deficit; cash not projected' : ', projected cash deficit') : ''}${(d.funding_gap ?? 0) > 0 ? `, annual bill funding gap ${fmt(d.funding_gap)}` : ''}`}
            onClick={() => selectMonth(d.month)}
            title={`Income ${money(d.income, currency)} · Budget expenses ${money(d.expenses, currency)} · Projected cash ${fmt(d.remaining_with_savings)} · Annual funding gap ${fmt(d.funding_gap ?? 0)}`}
          >
            <div className="bars">
              <i
                style={{ height: Math.max((d.income / max) * 100, 2) + '%' }}
              />
              <i
                style={{ height: Math.max((d.expenses / max) * 100, 2) + '%' }}
              />
            </div>
            <span>
              {new Date(d.month + '-02').toLocaleDateString(undefined, {
                month: 'short',
              })}
            </span>
            {(d.savings_adjusted_deficit || (d.funding_gap ?? 0) > 0) && (
              <span className="red">!</span>
            )}
          </button>
        ))}
      </div>
      <p className="chart-note">
        Markers flag a projected cash deficit or an annual bill funding gap.
        Cash carries forward from your recorded balance month, paying annual
        bills once at their due date. Bill funding uses only earmarked savings
        and that bill's planned contributions; other budget room is not
        automatically assigned. Months before the recorded balance are not
        projected. Without a cash estimate, markers use monthly budget deficits.
        Projected contributions are excluded from that balance.
        {data.some((d) => d.income_complete === false) &&
          ' Income is missing in some months; cash projections are incomplete.'}
      </p>
      <details>
        <summary>View annual forecast table</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Income</th>
                <th>Expenses</th>
                <th>Monthly remaining</th>
                <th>Projected cash</th>
                <th>Annual funding gap</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.month}>
                  <th>
                    <button
                      className="text-button"
                      onClick={() => selectMonth(d.month)}
                    >
                      {monthLabel(d.month, true)}
                    </button>
                  </th>
                  <td>{money(d.income, currency)}</td>
                  <td>{money(d.expenses, currency)}</td>
                  <td>{money(d.remaining, currency)}</td>
                  <td className={d.savings_adjusted_deficit ? 'red' : ''}>
                    {fmt(d.remaining_with_savings)}
                  </td>
                  <td className={(d.funding_gap ?? 0) > 0 ? 'red' : ''}>
                    {fmt(d.funding_gap ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
