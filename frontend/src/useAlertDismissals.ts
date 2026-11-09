import { useEffect, useState } from 'react';
import { api } from './api';

type AlertKind = 'forecast_deficit' | 'actual_deficit';
type Dismissal = { month: string; kind: AlertKind; dismissed_at: string };

export function useAlertDismissals() {
  const [dismissals, setDismissals] = useState<Dismissal[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    api<Dismissal[]>('/alerts/dismissals', 'GET', undefined, controller.signal)
      .then((records) => {
        if (active) setDismissals(records);
      })
      .catch(() => {
        if (active)
          setError(
            'Could not load dismissed budget alerts. Previously dismissed alerts may be shown. Reload to retry.',
          );
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);
  const dismiss = async (kind: AlertKind, month: string) => {
    setBusy(true);
    setError('');
    try {
      const record = await api<Dismissal>('/alerts/dismissals', 'POST', {
        kind,
        month,
      });
      setDismissals((records) => [
        ...records.filter((r) => r.kind !== kind || r.month !== month),
        record,
      ]);
    } catch {
      setError(
        'Could not save this dismissal. The budget alert remains visible; please retry.',
      );
    } finally {
      setBusy(false);
    }
  };
  const restore = async () => {
    setBusy(true);
    setError('');
    try {
      await api('/alerts/dismissals', 'DELETE');
      setDismissals([]);
    } catch {
      setError('Could not restore dismissed budget alerts. Please retry.');
    } finally {
      setBusy(false);
    }
  };
  return {
    ready,
    busy,
    error,
    count: dismissals.length,
    dismiss,
    restore,
    isDismissed: (kind: AlertKind, month: string) =>
      dismissals.some((r) => r.kind === kind && r.month === month),
  };
}
