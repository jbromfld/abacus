import { useEffect, useState } from 'react';
import { api } from './api';
import { useResourceRevision } from './resourceCache';
import type { Settings, Category, Account, Recurring, Forecast } from './api';

function useMetadata<T>(path: string, initial: T, revision: number) {
  const [data, setData] = useState(initial);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError('');
    api<T>(path, 'GET', undefined, controller.signal)
      .then((value) => {
        if (active) {
          setData(value);
          setReady(true);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, revision]);
  return { data, setData, loading, error, ready };
}

export function useWorkspace(month: string, revision = 0) {
  const settingsRevision = useResourceRevision(['settings']);
  const categoryRevision = useResourceRevision(['categories']);
  const accountRevision = useResourceRevision(['accounts']);
  const recurringRevision = useResourceRevision(['recurring']);
  const forecastRevision = useResourceRevision(['forecast']);
  const settings = useMetadata<Settings>(
    '/settings',
    {
      currency: 'USD',
      model: '',
      advisor_enabled: false,
      advisor_memory_enabled: false,
    },
    revision + settingsRevision,
  );
  const categories = useMetadata<Category[]>(
    '/categories',
    [],
    revision + categoryRevision,
  );
  const accounts = useMetadata<Account[]>(
    '/accounts',
    [],
    revision + accountRevision,
  );
  const recurring = useMetadata<Recurring[]>(
    '/recurring',
    [],
    revision + recurringRevision,
  );
  const [result, setResult] = useState<{
    month: string;
    forecast: Forecast | null;
    loading: boolean;
    error: string;
  }>({ month, forecast: null, loading: true, error: '' });
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setResult((previous) => ({
      month,
      forecast: previous.month === month ? previous.forecast : null,
      loading: true,
      error: '',
    }));
    api<Forecast>(
      `/forecast?month=${month}`,
      'GET',
      undefined,
      controller.signal,
    )
      .then((forecast) => {
        if (active) setResult({ month, forecast, loading: false, error: '' });
      })
      .catch((e) => {
        if (active)
          setResult({
            month,
            forecast: null,
            loading: false,
            error: e.message,
          });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [month, revision, forecastRevision]);
  const current = result.month === month;
  return {
    settings: settings.data,
    categories: categories.data,
    accounts: accounts.data,
    setAccounts: accounts.setData,
    recurring: recurring.data,
    forecast: current && settings.ready ? result.forecast : null,
    loading: !current || result.loading || settings.loading,
    error: [
      settings.error,
      categories.error,
      accounts.error,
      recurring.error,
      current ? result.error : '',
    ]
      .filter(Boolean)
      .join('; '),
  };
}
