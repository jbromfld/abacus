import { useEffect, useState } from 'react';
import { Check, LoaderCircle } from 'lucide-react';
import {
  api,
  inputAmount,
  money,
  monthLabel,
  nonnegativeMinor,
  digits,
} from './api';
import type { CategoryAverage, SpendingAverages } from './api';

function GuideRow({
  entry,
  currency,
  onChanged,
}: {
  entry: CategoryAverage;
  currency: string;
  onChanged: () => void;
}) {
  const [amount, setAmount] = useState(
    entry.monthly_guide === null
      ? ''
      : inputAmount(entry.monthly_guide, currency),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(
    () =>
      setAmount(
        entry.monthly_guide === null
          ? ''
          : inputAmount(entry.monthly_guide, currency),
      ),
    [entry.monthly_guide, currency],
  );
  const save = async (value: number | null) => {
    setBusy(true);
    setError('');
    try {
      await api('/categories/' + entry.id + '/guide', 'PATCH', {
        monthly_guide: value,
      });
      setAmount(value === null ? '' : inputAmount(value, currency));
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const saveInput = () => {
    try {
      void save(
        amount.trim() === '' ? null : nonnegativeMinor(amount, currency),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <tr>
      <th>{entry.name}</th>
      <td>
        {entry.average === null ? 'No data' : money(entry.average, currency)}
      </td>
      <td>
        <input
          aria-label={`Monthly planning guide for ${entry.name}`}
          type="number"
          min="0"
          step={10 ** -digits(currency)}
          disabled={busy}
          value={amount}
          placeholder="Not set"
          onChange={(e) => setAmount(e.target.value)}
        />
        {error && (
          <small role="alert" className="red">
            {error}
          </small>
        )}
      </td>
      <td>
        <div className="guide-actions">
          <button
            className="icon"
            aria-label={`Save planning guide for ${entry.name}`}
            disabled={busy}
            onClick={saveInput}
          >
            <Check size={15} />
          </button>
          <button
            className="text-button"
            aria-label={`Use suggested mean for ${entry.name}`}
            disabled={busy || entry.suggested_guide === null}
            onClick={() => void save(entry.suggested_guide)}
          >
            Use mean
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function CategoryAverages({
  end,
  selectedIds,
  currency,
  revision,
  onChanged,
}: {
  end: string;
  selectedIds: string[];
  currency: string;
  revision: number;
  onChanged: () => void;
}) {
  const key = JSON.stringify([end, selectedIds]);
  const [result, setResult] = useState<{
    key: string;
    data: SpendingAverages;
  } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const abort = new AbortController();
    setBusy(true);
    const [requestEnd, requestIds] = JSON.parse(key) as [string, string[]];
    const params = new URLSearchParams({ end: requestEnd });
    requestIds.forEach((id) => params.append('category_ids', id));
    api<SpendingAverages>(
      '/spending/averages?' + params,
      'GET',
      undefined,
      abort.signal,
    )
      .then((data) => {
        if (active) {
          setResult({ key, data });
          setError('');
        }
      })
      .catch((e) => {
        if (active && (e as Error).name !== 'AbortError') setError(e.message);
      })
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
      abort.abort();
    };
  }, [key, revision]);
  const data = result?.key === key ? result.data : null;
  const selected =
    data?.categories.filter((c) => selectedIds.includes(c.id)) ?? [];
  return (
    <div className="category-averages">
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
      {!data && busy && (
        <p role="status">
          <LoaderCircle size={14} className="spin" />
          Loading monthly averages…
        </p>
      )}
      {data && (
        <>
          <div className="average-summary">
            <div>
              <span>
                {selectedIds.length ? 'Selected categories' : 'All spending'} ·
                monthly mean
              </span>
              <strong>
                {data.average === null
                  ? 'No historical data'
                  : money(data.average, currency)}
              </strong>
            </div>
            <p>
              {data.sample_count} recorded past{' '}
              {data.sample_count === 1 ? 'month' : 'months'} ·{' '}
              {monthLabel(data.window_start, true)} –{' '}
              {monthLabel(data.window_end, true)}
              {data.partial_month_count > 0 && (
                <small className="red">
                  Includes {data.partial_month_count} incomplete{' '}
                  {data.partial_month_count === 1 ? 'month' : 'months'}; the
                  mean may be understated.
                </small>
              )}
            </p>
          </div>
          {selected.length > 0 && (
            <div className="average-categories">
              {selected.map((c) => (
                <span key={c.id}>
                  <strong>{c.name}</strong> · Mean{' '}
                  {c.average === null
                    ? 'not available'
                    : money(c.average, currency)}
                  {c.monthly_guide !== null && (
                    <> · Guide {money(c.monthly_guide, currency)}</>
                  )}
                </span>
              ))}
            </div>
          )}
          <details className="guide-editor">
            <summary>Category means & planning guides</summary>
            <p>
              Guides are references only. They never change forecast expenses,
              savings projections, or remaining budget. Use the mean as a
              suggestion, enter your own amount, or clear the field to remove a
              guide.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Monthly mean</th>
                    <th>Guide ({currency})</th>
                    <th>
                      <span className="sr-only">Guide actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((entry) => (
                    <GuideRow
                      key={entry.id}
                      entry={entry}
                      currency={currency}
                      onChanged={onChanged}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Missing, current, and future months are excluded. Explicitly
              complete zero-spending months count. Refunds reduce the mean; card
              payments and transfers do not count. Negative means suggest a zero
              guide.
            </p>
          </details>
        </>
      )}
    </div>
  );
}
