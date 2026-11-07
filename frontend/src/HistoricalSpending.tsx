import React, { useState, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { ChevronLeft, ChevronRight, LoaderCircle } from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import {
  api,
  money,
  monthLabel,
  shiftMonth,
  actualMonthFor,
  monthNow,
} from './api';
import type { Category, Trend } from './api';
import CategoryAverages from './CategoryAverages';
const colors = [
  '#548574',
  '#b6844d',
  '#7d76a3',
  '#6693ad',
  '#bd7478',
  '#8c9859',
  '#8a8d96',
];
export default function HistoricalSpending({
  categories,
  currency,
  revision,
  historyEnd,
  setHistoryEnd,
  selectedCats,
  setSelectedCats,
  overlay,
  setOverlay,
  drillMonth,
  refresh,
}: {
  categories: Category[];
  currency: string;
  revision: number;
  historyEnd: string;
  setHistoryEnd: Dispatch<SetStateAction<string>>;
  selectedCats: string[];
  setSelectedCats: Dispatch<SetStateAction<string[]>>;
  overlay: boolean;
  setOverlay: Dispatch<SetStateAction<boolean>>;
  drillMonth: (month: string) => void;
  refresh: () => void;
}) {
  const [trends, setTrends] = useState<Trend[]>([]);
  const [error, setError] = useState('');
  const fmt = (n: number) => money(n, currency);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setTrends([]);
    setError('');
    const params = new URLSearchParams({ end: historyEnd });
    selectedCats.forEach((id) => params.append('category_ids', id));
    api<Trend[]>('/trends?' + params, 'GET', undefined, controller.signal)
      .then((t) => active && setTrends(t))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
      controller.abort();
    };
  }, [historyEnd, revision, selectedCats]);
  const selectedCategories = categories.filter((c) =>
    selectedCats.includes(c.id),
  );
  const chartData = trends.map((t) => ({
    month: t.month,
    label: monthLabel(t.month, true),
    actual: t.actual,
    forecast: t.forecast,
    ...Object.fromEntries(
      selectedCategories.flatMap((c) => [
        [c.id, t.categories[c.id]?.actual],
        [c.id + '_forecast', t.categories[c.id]?.forecast],
      ]),
    ),
  }));
  return (
    <>
      {error && (
        <p role="alert" className="notice danger">
          {error}
        </p>
      )}
      <section className="panel historical-trends">
        <div className="section-head">
          <div>
            <h2>Spending, over time</h2>
            <p>
              12 months ending {monthLabel(historyEnd)} · refunds reduce
              spending
            </p>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={overlay}
              onChange={(e) => setOverlay(e.target.checked)}
            />
            Show forecast
          </label>
        </div>{' '}
        <div className="history-controls">
          <div
            className="month-stepper"
            role="group"
            aria-label="Historical chart ending month"
          >
            <button
              className="icon"
              aria-label="End chart one month earlier"
              disabled={historyEnd <= '1900-12'}
              onClick={() => setHistoryEnd(shiftMonth(historyEnd, -1))}
            >
              <ChevronLeft size={17} />
            </button>
            <label>
              Ending month
              <input
                type="month"
                min="1900-12"
                max="9998-12"
                value={historyEnd}
                onChange={(e) =>
                  e.target.value && setHistoryEnd(e.target.value)
                }
              />
            </label>
            <button
              className="icon"
              aria-label="End chart one month later"
              disabled={historyEnd >= '9998-12'}
              onClick={() => setHistoryEnd(shiftMonth(historyEnd, 1))}
            >
              <ChevronRight size={17} />
            </button>
          </div>
          <button
            className="secondary small"
            onClick={() => setHistoryEnd(actualMonthFor(monthNow()))}
          >
            Latest 12 months
          </button>
        </div>
        <div className="category-filters">
          <button
            className={!selectedCats.length ? 'chip selected' : 'chip'}
            onClick={() => setSelectedCats([])}
          >
            All categories
          </button>
          {categories.map((c, i) => (
            <button
              key={c.id}
              className={
                'chip ' + (selectedCats.includes(c.id) ? 'selected' : '')
              }
              onClick={() =>
                setSelectedCats((ids) =>
                  ids.includes(c.id)
                    ? ids.filter((id) => id !== c.id)
                    : [...ids, c.id],
                )
              }
            >
              <i style={{ background: colors[i % colors.length] }} />
              {c.name}
            </button>
          ))}
        </div>
        <CategoryAverages
          end={historyEnd}
          selectedIds={selectedCats}
          currency={currency}
          revision={revision}
          onChanged={refresh}
        />
        <div
          className="chart"
          aria-label="Monthly actual spending and forecast"
        >
          {!trends.length ? (
            <div className="history-loading" role="status">
              <LoaderCircle size={17} className="spin" />
              {error
                ? 'History could not be loaded. Adjust the ending month or try again.'
                : 'Loading spending history…'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                onClick={(state) => {
                  const point = chartData.find(
                    (p) => p.label === state.activeLabel,
                  );
                  if (point) drillMonth(point.month);
                }}
                margin={{ top: 16, right: 20, bottom: 8, left: 5 }}
              >
                <CartesianGrid
                  vertical={false}
                  stroke="#e8ece7"
                  strokeDasharray="3 5"
                />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11, fill: '#7d867e' }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={25}
                />
                <YAxis
                  tickFormatter={(n) => fmt(Number(n))}
                  tick={{ fontSize: 11, fill: '#7d867e' }}
                  axisLine={false}
                  tickLine={false}
                  width={85}
                />
                <Tooltip formatter={(value) => fmt(Number(value))} />
                {selectedCategories.length ? (
                  selectedCategories.map((c, i) => (
                    <React.Fragment key={c.id}>
                      <Line
                        isAnimationActive={false}
                        type="monotone"
                        dataKey={c.id}
                        name={c.name + ' actual'}
                        stroke={colors[i % colors.length]}
                        strokeWidth={2.5}
                        connectNulls={false}
                        dot={{ r: 3 }}
                      />
                      {overlay && (
                        <Line
                          isAnimationActive={false}
                          dataKey={c.id + '_forecast'}
                          name={c.name + ' forecast'}
                          stroke={colors[i % colors.length]}
                          strokeDasharray="5 5"
                          dot={false}
                        />
                      )}
                    </React.Fragment>
                  ))
                ) : (
                  <>
                    <Line
                      isAnimationActive={false}
                      dataKey="actual"
                      name="Actual spending"
                      stroke="#548574"
                      strokeWidth={3}
                      connectNulls={false}
                      dot={{ r: 3 }}
                    />
                    {overlay && (
                      <Line
                        isAnimationActive={false}
                        dataKey="forecast"
                        name="Forecast expenses"
                        stroke="#b6844d"
                        strokeDasharray="5 5"
                        dot={false}
                      />
                    )}
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
        <p className="chart-note">
          Solid lines: actual spending. Dashed lines: forecast. Gaps indicate
          missing records. Current and incomplete months are partial. Select a
          month on the chart or in its data table to explore its expense
          breakdown.
        </p>
        <details>
          <summary>View chart data as a table</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Status</th>
                  <th>Actual spending</th>
                  <th>Forecast expenses</th>
                  {selectedCategories.map((c) => (
                    <React.Fragment key={c.id}>
                      <th>{c.name} actual</th>
                      <th>{c.name} forecast</th>
                    </React.Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trends.map((t) => (
                  <tr key={t.month}>
                    <th>
                      <button
                        className="text-button"
                        onClick={() => drillMonth(t.month)}
                        aria-label={`View expense breakdown for ${monthLabel(t.month)}`}
                      >
                        {monthLabel(t.month, true)}
                      </button>
                    </th>
                    <td>{t.status}</td>
                    <td>{t.actual === null ? 'Missing' : fmt(t.actual)}</td>
                    <td>{fmt(t.forecast)}</td>
                    {selectedCategories.map((c) => (
                      <React.Fragment key={c.id}>
                        <td>
                          {t.categories[c.id]?.actual == null
                            ? 'Missing'
                            : fmt(t.categories[c.id].actual!)}
                        </td>
                        <td>{fmt(t.categories[c.id]?.forecast ?? 0)}</td>
                      </React.Fragment>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </>
  );
}
