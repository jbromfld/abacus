import { useEffect, useState } from 'react';
import { digits, inputAmount } from './api';

export default function AmountSlider({
  label,
  value,
  onChange,
  currency,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  currency: string;
  disabled?: boolean;
}) {
  const factor = 10 ** digits(currency);
  const amount = Number(value || 0) * factor;
  const [maximum, setMaximum] = useState(Math.max(10000 * factor, amount * 2));
  useEffect(() => {
    if (Number.isFinite(amount) && amount > maximum)
      setMaximum(Math.min(9_000_000_000_000, amount * 2));
  }, [amount, maximum]);
  return (
    <div className="amount-slider">
      <label>
        {label} ({currency})
        <input
          aria-label={label}
          type="number"
          min={1 / factor}
          max={9_000_000_000_000 / factor}
          step={1 / factor}
          required
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
      <input
        aria-label={`${label} slider`}
        type="range"
        min={factor}
        max={maximum}
        step={factor}
        disabled={disabled}
        value={Math.max(factor, Math.min(maximum, amount || 0))}
        onChange={(e) =>
          onChange(inputAmount(Number(e.target.value), currency))
        }
      />
    </div>
  );
}
