import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { api, digits, inputAmount, minor, money, monthLabel } from './api';

type Source = {
  id: string;
  year: number;
  name: string;
  amount: number;
  included: boolean;
  monthly_amounts: number[];
};
type Summary = {
  year: number;
  total: number;
  included_total: number;
  monthly_amounts: number[];
  sources: Source[];
};

function IncomeForm({
  source,
  year,
  currency,
  disabled,
  onSave,
  onRemove,
}: {
  source?: Source;
  year: number;
  currency: string;
  disabled: boolean;
  onSave: (data: Omit<Source, 'id' | 'monthly_amounts'>) => Promise<boolean>;
  onRemove?: () => void;
}) {
  const [name, setName] = useState(source?.name ?? '');
  const [amount, setAmount] = useState(
    inputAmount(source?.amount ?? 1000 * 10 ** digits(currency), currency),
  );
  const [included, setIncluded] = useState(source?.included ?? false);
  const [error, setError] = useState('');
  const factor = 10 ** digits(currency);
  const [maximum, setMaximum] = useState(
    Math.min(
      9_000_000_000_000,
      Math.max(10000 * factor, (source?.amount ?? 0) * 2),
    ),
  );
  const label = source?.name ?? 'New income source';
  const changed =
    !source ||
    name !== source.name ||
    Number(amount) * factor !== source.amount ||
    included !== source.included;
  return (
    <form
      className="annual-income-source"
      aria-label={source ? `Edit ${source.name}` : 'Add annual income source'}
      onSubmit={async (event) => {
        event.preventDefault();
        setError('');
        try {
          const saved = await onSave({
            name: name.trim(),
            year,
            amount: minor(amount, currency),
            included,
          });
          if (saved && !source) {
            setName('');
            setIncluded(false);
          }
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      <div className="form-grid">
        <label>
          {source ? 'Source' : 'New source'}
          <input
            aria-label={`${label} name`}
            required
            maxLength={160}
            value={name}
            placeholder="Tax refund, sale proceeds…"
            disabled={disabled}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Annual amount ({currency})
          <input
            aria-label={`${label} annual amount`}
            type="number"
            min={1 / factor}
            max={9_000_000_000_000 / factor}
            step={1 / factor}
            required
            value={amount}
            disabled={disabled}
            onChange={(e) => {
              setAmount(e.target.value);
              const value = Number(e.target.value) * factor;
              if (Number.isFinite(value) && value > maximum)
                setMaximum(Math.min(9_000_000_000_000, value * 2));
            }}
          />
        </label>
      </div>
      <input
        aria-label={`${label} annual amount slider`}
        type="range"
        min={factor}
        max={maximum}
        step={factor}
        value={Math.max(factor, Number(amount || 0) * factor)}
        disabled={disabled}
        onChange={(e) =>
          setAmount(inputAmount(Number(e.target.value), currency))
        }
      />
      <label className="checkbox">
        <input
          aria-label={`Include ${label} in monthly income`}
          type="checkbox"
          checked={included}
          disabled={disabled}
          onChange={(e) => setIncluded(e.target.checked)}
        />
        Include in monthly income for {year}
      </label>
      {source && (
        <p className="savings-hint">
          {source.included ? 'Included' : 'Excluded'} in the saved forecast.
          Edits take effect when saved.
        </p>
      )}
      {error && (
        <p role="alert" className="notice danger">
          {error}
        </p>
      )}
      <div className="button-group">
        <button disabled={disabled || !changed || !name.trim()}>
          {!source && <Plus size={14} />}
          {source ? 'Save estimate' : 'Add income source'}
        </button>
        {onRemove && (
          <button
            type="button"
            className="text-button"
            disabled={disabled}
            onClick={onRemove}
          >
            <Trash2 size={14} /> Remove {source?.name}
          </button>
        )}
      </div>
    </form>
  );
}

export default function AnnualExpectedIncome({
  year,
  currency,
  revision,
  onChanged,
}: {
  year: number;
  currency: string;
  revision: number;
  onChanged: () => void;
}) {
  const [report, setReport] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    api<Summary>(`/annual-income?year=${year}`)
      .then((value) => active && setReport(value))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [year, revision]);
  const current = report?.year === year ? report : null;
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try {
      await action();
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const disabled = busy || loading || !current;
  return (
    <section className="panel annual-income">
      <div className="section-head">
        <div>
          <h2>Annual expected income</h2>
          <p>
            {year} · extra income estimates, separate from regular monthly
            income.
          </p>
        </div>
        <strong>{current ? money(current.total, currency) : '…'}</strong>
      </div>
      <div className="annual-income-content">
        <p className="savings-hint">
          Track expected tax refunds, sale proceeds, or other variable income.
          Check a source to spread it over January–December of {year}. These are
          budget estimates, not confirmed monthly deposits; they do not repeat
          next year. Avoid entering income already recorded in recurring
          accounts.
        </p>
        {loading && <p role="status">Loading annual income…</p>}
        {error && (
          <p role="alert" className="notice danger">
            {error}
          </p>
        )}
        {current && (
          <>
            <p className="annual-income-total">
              {money(current.included_total, currency)} included in monthly
              forecasts for {year}.
            </p>
            <details>
              <summary>Monthly allocation of included estimates</summary>
              <div
                className="table-scroll"
                role="region"
                aria-label="Annual income monthly allocation"
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Extra income</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.monthly_amounts.map((amount, i) => (
                      <tr key={i}>
                        <th>
                          {monthLabel(
                            `${year}-${String(i + 1).padStart(2, '0')}`,
                          )}
                        </th>
                        <td>{money(amount, currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <div className="annual-income-sources">
              {current.sources.map((source) => (
                <IncomeForm
                  key={`${source.id}:${source.name}:${source.amount}:${source.included}:${currency}`}
                  source={source}
                  year={year}
                  currency={currency}
                  disabled={disabled}
                  onSave={(data) =>
                    perform(() =>
                      api(`/annual-income/${source.id}`, 'PUT', data),
                    )
                  }
                  onRemove={() =>
                    void perform(() =>
                      api(`/annual-income/${source.id}`, 'DELETE'),
                    )
                  }
                />
              ))}
              <IncomeForm
                key={`${year}:${currency}`}
                year={year}
                currency={currency}
                disabled={disabled}
                onSave={(data) =>
                  perform(() => api('/annual-income', 'POST', data))
                }
              />
            </div>
          </>
        )}
      </div>
    </section>
  );
}
