import { useState, useEffect } from 'react';
import { api, monthLabel, money } from './api';
import type { Forecast } from './api';
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
  const [data, setData] = useState<Forecast[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api<Forecast[]>(`/forecasts?start=${year}-01&months=12`)
      .then((d) => {
        if (active) {
          setData(d);
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
            className={'year-month ' + (d.deficit ? 'over' : '')}
            aria-label={`${monthLabel(d.month)}: income ${money(d.income, currency)}, expenses ${money(d.expenses, currency)}${d.deficit ? ', over budget' : ''}`}
            onClick={() => selectMonth(d.month)}
            title={`Income ${money(d.income, currency)} · Expenses ${money(d.expenses, currency)}`}
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
            {d.deficit && <span className="red">!</span>}
          </button>
        ))}
      </div>
      <details>
        <summary>View annual forecast table</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Income</th>
                <th>Expenses</th>
                <th>Remaining</th>
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
                  <td className={d.deficit ? 'red' : ''}>
                    {money(d.remaining, currency)}
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
