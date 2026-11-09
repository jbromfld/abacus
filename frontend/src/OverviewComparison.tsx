import { useEffect, useState } from 'react';
import { api } from './api';
import AdvisorComparison from './AdvisorComparison';
import type { SpendingComparison } from './AdvisorComparison';

export default function OverviewComparison({
  currency,
  revision,
}: {
  currency: string;
  revision: number;
}) {
  const [comparison, setComparison] = useState<SpendingComparison | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    api<{ comparison: SpendingComparison | null }>(
      '/spending/comparison',
      'GET',
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (active) {
          setComparison(value.comparison);
          setError('');
        }
      })
      .catch((e) => {
        if (active && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [revision, refresh]);
  useEffect(() => {
    const visible = () => {
      if (!document.hidden) setRefresh((n) => n + 1);
    };
    const timer = setInterval(visible, 300000);
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('focus', visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('focus', visible);
    };
  }, []);
  return (
    <>
      {error && (
        <div className="notice danger" role="alert">
          Could not refresh the spending comparison. {error}{' '}
          <button
            className="text-button"
            onClick={() => setRefresh((n) => n + 1)}
          >
            Retry comparison
          </button>
        </div>
      )}
      {comparison ? (
        <AdvisorComparison
          comparison={comparison}
          currency={currency}
          periodDescription="Latest two finished months, independent of the selected forecast month."
        />
      ) : (
        !error && (
          <section className="panel">
            <div className="section-head">
              <div>
                <h2>What changed this month?</h2>
                <p role="status">Loading the latest two finished months…</p>
              </div>
            </div>
          </section>
        )
      )}
    </>
  );
}
