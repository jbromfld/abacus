import { useEffect, useState } from 'react';
import { api } from './api';
import type {
  Settings,
  Category,
  Account,
  Recurring,
  Purchase,
  Forecast,
  ImportSummary,
} from './api';
export function useWorkspace(month: string, revision: number) {
  const [settings, setSettings] = useState<Settings>({
    currency: 'USD',
    model: '',
    advisor_enabled: false,
    advisor_memory_enabled: false,
    reserve_alerts_enabled: true,
    reserve_checkpoint_day: 1,
  });
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [recurring, setRecurring] = useState<Recurring[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [imports, setImports] = useState<ImportSummary[]>([]);
  const [result, setResult] = useState<{
    month: string;
    forecast: Forecast | null;
    loading: boolean;
    error: string;
  }>({ month, forecast: null, loading: true, error: '' });
  const [metadataReady, setMetadataReady] = useState(false);
  const [metadataLoading, setMetadataLoading] = useState(true);
  const [metadataError, setMetadataError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setMetadataError('');
    setMetadataLoading(true);
    Promise.all([
      api<Settings>('/settings', 'GET', undefined, controller.signal),
      api<Category[]>('/categories', 'GET', undefined, controller.signal),
      api<Account[]>('/accounts', 'GET', undefined, controller.signal),
      api<Recurring[]>('/recurring', 'GET', undefined, controller.signal),
      api<Purchase[]>('/purchases', 'GET', undefined, controller.signal),
      api<ImportSummary[]>('/imports', 'GET', undefined, controller.signal),
    ])
      .then(([s, c, a, r, p, i]) => {
        if (active) {
          setSettings(s);
          setCategories(c);
          setAccounts(a);
          setRecurring(r);
          setPurchases(p);
          setImports(i);
          setMetadataReady(true);
        }
      })
      .catch((e) => {
        if (active) setMetadataError(e.message);
      })
      .finally(() => {
        if (active) setMetadataLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [revision]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
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
      .then((f) => {
        if (active)
          setResult({ month, forecast: f, loading: false, error: '' });
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
  }, [month, revision]);
  const current = result.month === month;
  return {
    settings,
    categories,
    accounts,
    setAccounts,
    recurring,
    purchases,
    imports,
    forecast: current && metadataReady ? result.forecast : null,
    loading: !current || result.loading || metadataLoading,
    error: metadataError || (current ? result.error : ''),
  };
}
