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
              'year-month ' + (d.savings_adjusted_deficit ? 'over' : '')
            }
            aria-label={`${monthLabel(d.month)}: income ${money(d.income, currency)}, expenses ${money(d.expenses, currency)}${d.savings_adjusted_deficit ? ', deficit after savings' : d.deficit ? ', monthly shortfall covered by current savings' : ''}; remaining plus savings ${money(d.remaining_with_savings, currency)}`}
            onClick={() => selectMonth(d.month)}
            title={`Income ${money(d.income, currency)} · Expenses ${money(d.expenses, currency)} · Monthly remaining + current savings ${money(d.remaining_with_savings, currency)}`}
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
            {d.savings_adjusted_deficit && <span className="red">!</span>}
          </button>
        ))}
      </div>
      <p className="chart-note">
        Deficit markers use monthly forecast remaining plus your current
        manually entered savings, checking each month independently. This does
        not project a running savings balance.{' '}
        {data.length > 0 &&
          (data[0].savings_balance === null
            ? 'Savings is not set, so markers use the monthly budget alone.'
            : `Current savings: ${money(data[0].savings_balance, currency)}.`)}
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
                <th>Remaining + current savings</th>
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
                    {money(d.remaining_with_savings, currency)}
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
