import { useEffect, useMemo, useState } from 'react';
import { Check, LoaderCircle } from 'lucide-react';
import { api, digits, inputAmount, monthNow, nonnegativeMinor } from './api';
import type { SavingsSnapshot } from './api';

export default function SavingsSettings({
  currency,
  onChanged,
}: {
  currency: string;
  onChanged: () => void;
}) {
  const [saved, setSaved] = useState<SavingsSnapshot | null>(null);
  const [amount, setAmount] = useState('');
  const [month, setMonth] = useState(monthNow());
  const [floor, setFloor] = useState('0');
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const factor = 10 ** digits(currency);
  const [maximum, setMaximum] = useState(10000 * factor);
  useEffect(() => {
    let active = true;
    setReady(false);
    api<SavingsSnapshot>('/savings')
      .then((value) => {
        if (!active) return;
        setSaved(value);
        setAmount(
          value.amount === null ? '' : inputAmount(value.amount, currency),
        );
        setMonth(value.month);
        setFloor(inputAmount(value.floor, currency));
        setMaximum(
          Math.max(
            10000 * factor,
            Math.ceil((value.amount ?? 0) / factor / 1000) * 2000 * factor,
          ),
        );
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setReady(true));
    return () => {
      active = false;
    };
  }, [currency]);
  const inputs = useMemo(() => {
    try {
      return amount && month
        ? {
            amount: nonnegativeMinor(amount, currency),
            month,
            floor: floor ? nonnegativeMinor(floor, currency) : 0,
          }
        : null;
    } catch {
      return null;
    }
  }, [amount, month, floor, currency]);
  const dirty =
    !!inputs &&
    (!saved ||
      inputs.amount !== saved.amount ||
      month !== saved.month ||
      inputs.floor !== saved.floor);
  const save = async () => {
    if (!inputs) return;
    setBusy(true);
    setError('');
    try {
      setSaved(await api<SavingsSnapshot>('/savings', 'PUT', inputs));
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel savings-settings">
      <div className="section-head">
        <div>
          <h2>Savings</h2>
          <p>
            Your saved starting balance for Purchase planner and Budget advisor.
          </p>
        </div>
      </div>
      <div className="savings-controls">
        {!ready && (
          <p role="status">
            <LoaderCircle size={15} className="spin" />
            Loading savings…
          </p>
        )}
        <label>
          Starting savings ({currency})
          <input
            aria-label="Starting savings amount"
            disabled={!ready || busy}
            type="number"
            min="0"
            step={1 / factor}
            value={amount}
            placeholder="Enter your savings"
            onChange={(e) => {
              setAmount(e.target.value);
              const value = Number(e.target.value) * factor;
              if (Number.isFinite(value) && value > maximum)
                setMaximum(Math.ceil(value / factor / 1000) * 2000 * factor);
            }}
          />
        </label>
        <input
          aria-label="Starting savings slider"
          type="range"
          min="0"
          max={maximum}
          step={100 * factor}
          disabled={!ready || busy}
          value={Math.max(0, Math.min(maximum, Number(amount || 0) * factor))}
          onChange={(e) =>
            setAmount(inputAmount(Number(e.target.value), currency))
          }
        />
        <div className="savings-input-grid">
          <label>
            Balance month
            <input
              type="month"
              value={month}
              disabled={!ready || busy}
              onChange={(e) => setMonth(e.target.value)}
            />
          </label>
          <label>
            Savings floor ({currency})
            <input
              type="number"
              min="0"
              step={1 / factor}
              value={floor}
              disabled={!ready || busy}
              onChange={(e) => setFloor(e.target.value)}
            />
          </label>
        </div>
        <p className="savings-hint">
          Use the balance at the start of this month. Saving a past/current
          month also records that dated balance for reserve checks; it never
          resets the reserve target. Savings is separate from recurring income
          and expenses; scenarios use it without adding it to monthly income.
        </p>
        {error && (
          <p role="alert" className="notice danger">
            {error}
          </p>
        )}
        <button disabled={!ready || busy || !dirty} onClick={() => void save()}>
          <Check size={14} />
          {saved?.amount !== null && saved && !dirty
            ? 'Savings saved'
            : busy
              ? 'Saving…'
              : 'Save savings'}
        </button>
      </div>
    </section>
  );
}
