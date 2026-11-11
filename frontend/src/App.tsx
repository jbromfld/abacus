import React, { useState, useEffect, lazy, Suspense } from 'react';
import {
  LayoutDashboard,
  Repeat2,
  ShoppingBag,
  ChartNoAxesCombined,
  Settings2,
  ArrowDownLeft,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Plus,
  X,
  ArrowRight,
  Upload,
  Leaf,
  AlertTriangle,
  Pencil,
  Trash2,
  LoaderCircle,
  MessageCircle,
  RotateCcw,
} from 'lucide-react';
import {
  api,
  monthNow,
  shiftMonth,
  actualMonthFor,
  monthLabel,
  loadImport,
  money,
  inputAmount,
  minor,
} from './api';
import type {
  Category,
  Account,
  Recurring,
  Transaction,
  Forecast,
  ImportJob,
  ImportUpdate,
} from './api';
import { useAlertDismissals } from './useAlertDismissals';
import './style.css';
const BudgetAdvisor = lazy(() => import('./BudgetAdvisor'));
const AdvisorMemory = lazy(() => import('./AdvisorMemory'));
const ExpenseBreakdown = lazy(() => import('./ExpenseBreakdown'));
const BatchUploadDialog = lazy(() => import('./BatchUploadDialog'));
import { importStage } from './batchStatus';
import UpcomingBills from './UpcomingBills';
import AnnualExpectedIncome from './AnnualExpectedIncome';
import Planning, { PlanningCategories, PlanningOverview } from './Planning';
import type { PlanDraft } from './Planning';
import RememberedPayees from './RememberedPayees';
const HistoricalSpending = lazy(() => import('./HistoricalSpending'));
const ImportReview = lazy(() => import('./ImportReview'));
import FormEditor from './FormEditor';
import type { Field, Editor } from './FormEditor';
import OverviewComparison from './OverviewComparison';
import YearSummary from './YearSummary';
import { useWorkspace } from './useWorkspace';
import { invalidateResources, useResourceRevision } from './resourceCache';
import { usePagedRecords } from './usePagedRecords';
import type { ImportSummary } from './api';

const colors = [
  '#548574',
  '#b6844d',
  '#7d76a3',
  '#6693ad',
  '#bd7478',
  '#8c9859',
  '#8a8d96',
];
const kinds = ['purchase', 'refund', 'fee', 'payment', 'transfer'];

function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Leaf size={26} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState('Overview');
  const budgetAlerts = useAlertDismissals();
  const [advisorVisited, setAdvisorVisited] = useState(false);
  useEffect(() => {
    if (view === 'Budget advisor') setAdvisorVisited(true);
  }, [view]);
  const [advisorEntry, setAdvisorEntry] = useState<{
    question: string;
    key: number;
  } | null>(null);
  const [advisorPlanId, setAdvisorPlanId] = useState<string | null>(null);
  const [planDraft, setPlanDraft] = useState<{
    key: number;
    value: PlanDraft;
  } | null>(null);
  const [month, setMonth] = useState(monthNow());
  const [spendingMode, setSpendingMode] = useState<
    'breakdown' | 'entries' | 'transactions' | 'historical'
  >('breakdown');
  const [historyEnd, setHistoryEnd] = useState(() =>
    actualMonthFor(monthNow()),
  );
  const [scrollToBreakdown, setScrollToBreakdown] = useState(false);
  const [currentActual, setCurrentActual] = useState(false);
  const actualMonth = actualMonthFor(month, currentActual);
  const [actualReport, setActualReport] = useState<Forecast | null>(null);
  const [actualLoading, setActualLoading] = useState(true);
  const revision = useResourceRevision([
    'settings',
    'categories',
    'accounts',
    'recurring',
    'forecast',
    'planning',
    'imports',
  ]);
  const transactionRevision = useResourceRevision(['transactions']);
  const importRevision = useResourceRevision(['imports']);
  const {
    settings,
    categories,
    accounts,
    setAccounts,
    recurring,
    forecast,
    loading,
    error: loadError,
  } = useWorkspace(month);
  const [error, setError] = useState('');
  const [editor, setEditor] = useState<Editor | null>(null);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [importUpdate, setImportUpdate] = useState<ImportUpdate | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadAccount, setUploadAccount] = useState('');
  const [uploadPeriod, setUploadPeriod] = useState<string | null>(null);
  const [monitoring, setMonitoring] = useState<string | null>(null);
  const [selectedCats, setSelectedCats] = useState<string[]>([]);
  const [overlay, setOverlay] = useState(true);
  const [query, setQuery] = useState('');
  const transactionPage = usePagedRecords<Transaction>(
    `/transactions?month=${actualMonth}&q=${encodeURIComponent(query)}`,
    view === 'Spending' && spendingMode === 'transactions',
    transactionRevision,
  );
  const transactions = transactionPage.items;
  const importPage = usePagedRecords<ImportSummary>(
    '/imports',
    view === 'Statement imports',
    importRevision,
  );
  const imports = importPage.items;
  const [models, setModels] = useState<{ models: string[]; error: string }>({
    models: [],
    error: '',
  });
  const drillMonth = (value: string) => {
    setCurrentActual(true);
    setMonth(value);
    setSpendingMode('breakdown');
    setScrollToBreakdown(true);
  };
  useEffect(() => {
    if (
      scrollToBreakdown &&
      view === 'Spending' &&
      spendingMode === 'breakdown'
    ) {
      document
        .getElementById('expense-breakdown')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setScrollToBreakdown(false);
    }
  }, [scrollToBreakdown, view, spendingMode]);
  const refresh = () => invalidateResources('/transactions');
  const openOverview = () => {
    setMonth(monthNow());
    setView('Overview');
    refresh();
  };
  const currency = settings.currency;
  const fmt = (n: number) => money(n, currency);
  const catName = (id: string | null) =>
    categories.find((c) => c.id === id)?.name ?? 'Income';
  const act = async (action: () => Promise<unknown>) => {
    try {
      setError('');
      await action();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setActualLoading(true);
    api<Forecast>(
      `/forecast?month=${actualMonth}`,
      'GET',
      undefined,
      controller.signal,
    )
      .then((report) => {
        if (active) setActualReport(report);
      })
      .catch((e) => {
        if (active && (e as Error).name !== 'AbortError')
          setError((e as Error).message);
      })
      .finally(() => {
        if (active) setActualLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [actualMonth, revision]);

  useEffect(() => {
    if (view === 'Settings') {
      if (settings.advisor_enabled)
        api<typeof models>('/models')
          .then(setModels)
          .catch((e) => setError(e.message));
    }
  }, [view, revision, settings.advisor_enabled]);
  useEffect(() => {
    if (view === 'Budget advisor' && !settings.advisor_enabled)
      setView('Settings');
  }, [view, settings.advisor_enabled]);
  useEffect(() => {
    let active = true;
    const updateCards = () => {
      api<Account[]>('/accounts')
        .then((cards) => {
          if (active) setAccounts(cards);
        })
        .catch(() => {
          if (active)
            setError(
              'Could not refresh card freshness alerts. Check the local server.',
            );
        });
    };
    const timer = setInterval(updateCards, 60000);
    const onVisible = () => {
      if (!document.hidden) updateCards();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [setAccounts]);
  const monitorCard = async (id: string, enabled: boolean) => {
    setMonitoring(id);
    setError('');
    try {
      const updated = await api<Account>(
        '/accounts/' + id + '/monitoring',
        'PATCH',
        { stale_alert_enabled: enabled },
      );
      setAccounts((cards) =>
        cards.map((card) => (card.id === id ? updated : card)),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMonitoring(null);
    }
  };
  const staleCards = accounts.filter((card) => card.stale);
  const categoryOptions = [
    { value: '', label: 'Choose category' },
    ...categories.map((c) => ({ value: c.id, label: c.name })),
  ];
  const accountOptions = [
    { value: '', label: 'Choose account' },
    ...accounts.map((c) => ({ value: c.id, label: c.name })),
  ];
  const amountField = (amount?: number): Field => ({
    name: 'amount',
    label: `Amount (${currency})`,
    type: 'number',
    value: amount ? inputAmount(amount, currency) : '',
  });
  const openRecurring = (r?: Recurring) =>
    setEditor({
      title: r ? 'Edit recurring account' : 'Add recurring account',
      description: r
        ? 'Changes here apply to the schedule. Use “Adjust amount” for changes that start in a specific month.'
        : 'Add a regular bill or income. Enter the yearly total for annual bills and choose whether to distribute it. Annual income stays in its scheduled month.',
      fields: [
        { name: 'name', label: 'Name', value: r?.name },
        {
          name: 'kind',
          label: 'Direction',
          value: r?.kind ?? 'payable',
          options: [
            { value: 'payable', label: 'Payable · money out' },
            { value: 'receivable', label: 'Receivable · money in' },
          ],
        },
        {
          name: 'frequency',
          label: 'Frequency',
          value: r?.frequency ?? 'monthly',
          options: [
            { value: 'monthly', label: 'Monthly' },
            { value: 'annual', label: 'Annual' },
          ],
        },
        {
          name: 'distribute_annual',
          label: 'Distribute annual expense across 12 months',
          type: 'checkbox',
          value: String(r?.distribute_annual ?? true),
          showWhen: { frequency: 'annual', kind: 'payable' },
          hint: 'Checked: spread the annual total monthly (for example, taxes). Unchecked: count the full total in the first month and its yearly anniversaries (for example, a subscription). Changing this setting recalculates the entire forecast schedule.',
        },
        {
          name: 'category_id',
          label: 'Category (required for payables)',
          value: r?.category_id ?? '',
          options: categoryOptions,
          required: false,
        },
        ...(!r
          ? [
              {
                ...amountField(),
                hint: 'For annual payables, enter the full yearly total. The distribution checkbox controls when it counts.',
              },
            ]
          : []),
        {
          name: 'start_month',
          label: 'First month',
          type: 'month',
          value: r?.start_month ?? month,
          hint: r
            ? 'Changes the active range and annual schedule anchor. Amount changes keep their dates.'
            : undefined,
        },
        {
          name: 'end_month',
          label: 'Final month (optional)',
          type: 'month',
          value: r?.end_month ?? '',
          required: false,
        },
        {
          name: 'due_day',
          label: 'Bill due day (1–31)',
          type: 'number',
          value: r?.due_day ?? '',
          min: 1,
          max: 31,
          required: false,
          showWhen: { kind: 'payable' },
          hint: r?.ach_day
            ? `Optional contractual due date, separate from ACH debit day ${r.ach_day}. Leave blank to use the ACH schedule.`
            : 'Optional. Leave blank for budget allowances such as groceries, entertainment, or medical copays. Only bills need due dates.',
        },
        {
          name: 'due_month',
          label: 'Annual bill due month',
          value: String(
            r?.due_month ?? Number((r?.start_month ?? month).slice(5)),
          ),
          options: Array.from({ length: 12 }, (_, i) => ({
            value: String(i + 1),
            label: new Date(2026, i, 2).toLocaleDateString(undefined, {
              month: 'long',
            }),
          })),
          required: false,
          showWhen: { frequency: 'annual', kind: 'payable' },
          hint: 'With a due day, this sets the annual payment month. Non-distributed annual forecasts count the full bill in this month.',
        },
        {
          name: 'payment_tracking_start',
          label: 'Track payments from',
          type: 'date',
          value: r?.payment_tracking_start ?? '',
          required: false,
          showWhen: { kind: 'payable' },
          hint: 'Manual bills default to tracking from today when you first set a due day. ACH uses its recording start when no due date is set. Budget allowances do not need payment tracking.',
        },
        {
          name: 'ach_enabled',
          label: 'ACH · automatically record monthly actual spending',
          type: 'checkbox',
          value: String(r?.ach_enabled ?? false),
        },
        {
          name: 'ach_account_id',
          label: 'ACH bank account',
          value: r?.ach_account_id ?? '',
          options: accountOptions,
          required: false,
          hint: 'Add a named bank account in Settings. Required when automatic ACH recording is enabled.',
        },
        {
          name: 'ach_day',
          label: 'ACH debit day (1–31)',
          type: 'number',
          value: r?.ach_day ?? '',
          min: 1,
          max: 31,
          required: false,
          hint: 'Monthly payables only. Days beyond the end of a month use its last day.',
        },
        {
          name: 'ach_start_month',
          label: 'Record ACH actuals from',
          type: 'month',
          value: r?.ach_start_month ?? monthNow(),
          required: false,
          hint: 'Past due months from this month will be recorded immediately; existing actuals are not reconciled automatically.',
        },
      ],
      submit: async (d) => {
        await api(r ? `/recurring/${r.id}` : '/recurring', r ? 'PUT' : 'POST', {
          ...d,
          due_day: d.kind === 'payable' && d.due_day ? Number(d.due_day) : null,
          due_month:
            d.kind === 'payable' && d.frequency === 'annual' && d.due_day
              ? Number(d.due_month)
              : null,
          payment_tracking_start:
            d.kind === 'payable' && d.payment_tracking_start
              ? d.payment_tracking_start
              : null,
          distribute_annual:
            d.frequency === 'annual' && d.kind === 'payable'
              ? d.distribute_annual === 'on'
              : (r?.distribute_annual ?? true),
          ach_enabled: d.ach_enabled === 'on',
          ach_day: d.ach_day ? Number(d.ach_day) : null,
          ach_account_id: d.ach_account_id || null,
          ach_start_month: d.ach_start_month || null,
          start_month: d.start_month,
          end_month: d.end_month || null,
          category_id: d.category_id || null,
          ...(!r ? { amount: minor(d.amount, currency) } : {}),
        });
      },
    });
  const adjustRecurring = (r: Recurring) =>
    setEditor({
      title: `Adjust ${r.name}`,
      description:
        r.frequency === 'annual' && r.kind === 'payable'
          ? r.distribute_annual
            ? 'Enter an annual total; forecasts allocate one twelfth per month. A one-month override changes only that month’s allocation.'
            : `Enter the annual total, counted in full each ${new Date(2026, (r.due_month ?? Number(r.start_month.slice(5))) - 1, 2).toLocaleDateString(undefined, { month: 'long' })}. A one-month override must use a scheduled forecast month; an ongoing rate change applies to subsequent scheduled months.`
          : 'A monthly override affects only that month. An ongoing change preserves earlier amounts.',
      fields: [
        {
          name: 'month',
          label: 'Effective month',
          type: 'month',
          value: month,
        },
        r.frequency === 'annual' && r.kind === 'payable'
          ? { ...amountField(), label: `Annual total (${currency})` }
          : amountField(),
        {
          name: 'override',
          label: 'Apply change',
          value: 'false',
          options: [
            { value: 'false', label: 'From this month onward' },
            { value: 'true', label: 'Only this month' },
          ],
        },
      ],
      submit: async (d) => {
        await api(`/recurring/${r.id}/amount`, 'PUT', {
          month: d.month,
          amount: minor(d.amount, currency),
          override: d.override === 'true',
        });
      },
    });
  const openTransaction = (t?: Transaction) =>
    setEditor({
      title: t ? 'Edit transaction' : 'Record a transaction',
      fields: [
        { name: 'description', label: 'Description', value: t?.description },
        amountField(t?.amount),
        {
          name: 'date',
          label: 'Transaction date',
          type: 'date',
          value: t?.date ?? actualMonth + '-01',
        },
        {
          name: 'kind',
          label: 'Type',
          value: t?.kind ?? 'purchase',
          options: kinds.map((k) => ({
            value: k,
            label: k[0].toUpperCase() + k.slice(1),
          })),
        },
        {
          name: 'category_id',
          label: 'Category (optional for payments/transfers)',
          value: t?.category_id ?? '',
          options: categoryOptions,
          required: false,
        },
        {
          name: 'account_id',
          label: 'Bank or card account',
          value: t?.account_id ?? '',
          options: accountOptions,
        },
      ],
      submit: async (d) => {
        await api(
          t ? `/transactions/${t.id}` : '/transactions',
          t ? 'PUT' : 'POST',
          {
            ...d,
            amount: minor(d.amount, currency),
            category_id: d.category_id || null,
          },
        );
      },
    });
  const manageName = (type: 'categories' | 'accounts', item?: Category) =>
    setEditor({
      title: `${item ? 'Edit' : 'Add'} ${type === 'categories' ? 'category' : 'bank or card account'}`,
      fields: [{ name: 'name', label: 'Name', value: item?.name }],
      submit: async (d) => {
        await api(
          '/' + type + (item ? '/' + item.id : ''),
          item ? 'PUT' : 'POST',
          d,
        );
      },
    });
  const remove = (path: string, name: string) => {
    if (window.confirm(`Delete ${name}? This cannot be undone.`))
      void act(() => api(path, 'DELETE'));
  };
  const startImport = () => {
    setUploadAccount('');
    setUploadPeriod(actualMonth);
    setUploading(true);
  };
  const openImport = async (id: string) => {
    const j = await loadImport(id);
    setImportJob(j);
  };
  const actualData = actualReport?.month === actualMonth ? actualReport : null;
  const actualBusy = actualLoading && !actualData;
  const filteredTransactions = (actualData ? transactions : []).filter((t) =>
    t.description.toLowerCase().includes(query.toLowerCase()),
  );
  const nav = [
    { name: 'Overview', icon: LayoutDashboard },
    { name: 'Spending', icon: ChartNoAxesCombined },
    { name: 'Recurring accounts', icon: Repeat2 },
    { name: 'Planning', icon: ShoppingBag },
    { name: 'Statement imports', icon: Upload },
    ...(settings.advisor_enabled
      ? [{ name: 'Budget advisor', icon: MessageCircle }]
      : []),
  ];
  return (
    <Suspense fallback={<p role="status">Loading workspace…</p>}>
      <div className="app-shell">
        <aside className="sidebar">
          <a
            className="brand"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              openOverview();
            }}
          >
            <span className="brand-mark">
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
            </span>
            abacus<span className="brand-dot">.</span>
          </a>
          <p className="sidebar-label">YOUR MONEY, IN VIEW</p>
          <nav>
            {nav.map((n) => (
              <button
                key={n.name}
                className={'nav-item ' + (view === n.name ? 'active' : '')}
                onClick={() =>
                  n.name === 'Overview' ? openOverview() : setView(n.name)
                }
              >
                <n.icon size={19} />
                {n.name}
                {view === n.name && <span className="nav-dot" />}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="local-badge">
              <span />
              Local & personal
            </div>
            <p>
              A little clarity.
              <br />A little more possibility.
            </p>
            <button
              className={'nav-item ' + (view === 'Settings' ? 'active' : '')}
              onClick={() => setView('Settings')}
            >
              <Settings2 size={18} />
              Settings
            </button>
          </div>
        </aside>
        <main>
          <header className="topbar">
            <span className="breadcrumb">
              Your workspace <span>/</span> <strong>{view}</strong>
            </span>
            <div className="topbar-actions">
              <span className="private-label">
                <span className="status-dot" />
                Stored on your device
              </span>
              <button className="import-shortcut" onClick={startImport}>
                <Upload size={16} />
                Import statements
              </button>
            </div>
          </header>
          <div className="page">
            <div className="page-heading">
              <div>
                <p className="eyebrow">A LITTLE CLARITY FOR YOUR MONEY</p>
                <h1>
                  {view === 'Overview'
                    ? 'Make room for what matters.'
                    : view === 'Recurring accounts'
                      ? 'The regular things.'
                      : view === 'Planning'
                        ? 'A little looking ahead.'
                        : view === 'Spending'
                          ? 'See where it goes.'
                          : view === 'Statement imports'
                            ? 'Bring your spending up to date.'
                            : view === 'Budget advisor'
                              ? 'A little perspective for your plans.'
                              : 'Make yourself at home.'}
                </h1>
                <p className="subtitle">
                  {view === 'Overview'
                    ? 'Your month, thoughtfully laid out. One less thing on your mind.'
                    : view === 'Recurring accounts'
                      ? 'Give your bills and income a predictable place.'
                      : view === 'Planning'
                        ? 'A name, an amount, and a date. Make room for what matters.'
                        : view === 'Spending'
                          ? 'Small details, a clearer picture. Explore your spending over time.'
                          : view === 'Statement imports'
                            ? 'Upload statements, continue a review, or revisit a saved import.'
                            : view === 'Budget advisor'
                              ? 'Talk through a purchase with your local model and the numbers behind it.'
                              : 'Your categories, accounts, and optional local tools, all in one place.'}
                </p>
              </div>
              {view !== 'Settings' &&
                !(view === 'Spending' && spendingMode === 'historical') && (
                  <div className="month-picker">
                    <button
                      className="icon"
                      aria-label="Previous month"
                      onClick={() => setMonth(shiftMonth(month, -1))}
                    >
                      <ChevronLeft size={17} />
                    </button>
                    <label>
                      <span className="sr-only">Selected month</span>
                      <input
                        type="month"
                        value={month}
                        onChange={(e) =>
                          e.target.value && setMonth(e.target.value)
                        }
                      />
                    </label>
                    <button
                      className="icon"
                      aria-label="Next month"
                      onClick={() => setMonth(shiftMonth(month, 1))}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                )}
            </div>
            {staleCards.length > 0 && (
              <section
                className="notice card-freshness-alert"
                role="alert"
                aria-label="Credit card information needs updating"
              >
                <div className="card-alert-title">
                  <AlertTriangle size={18} />
                  <strong>Card information needs an update</strong>
                </div>
                {staleCards.map((card) => (
                  <div className="card-alert-row" key={card.id}>
                    <span>
                      <strong>{card.name}</strong> —{' '}
                      {card.last_information_date
                        ? `information through ${card.last_information_date} (${card.days_since_update} days old)`
                        : 'no saved information yet'}
                      .
                    </span>
                    <button
                      className="text-button"
                      onClick={() => {
                        setMonth(monthNow());
                        setView('Spending');
                        setUploadAccount(card.id);
                        setUploadPeriod(monthNow());
                        setUploading(true);
                      }}
                    >
                      Import statement <ArrowRight size={14} />
                    </button>
                  </div>
                ))}
              </section>
            )}
            {budgetAlerts.error && (
              <p className="notice danger" role="alert">
                {budgetAlerts.error}
              </p>
            )}
            {(error || loadError) && (
              <div className="notice danger" role="alert">
                <AlertTriangle size={18} />
                <span>{error || loadError}</span>
                <button
                  className="text-button"
                  onClick={() => {
                    setError('');
                    refresh();
                  }}
                >
                  Retry
                </button>
                {error && (
                  <button
                    className="icon"
                    aria-label="Dismiss error"
                    onClick={() => setError('')}
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            )}
            {loading && forecast && (
              <p className="notice" role="status">
                Updating budget…
              </p>
            )}
            {loading && !forecast ? (
              <div className="empty">
                <LoaderCircle className="spin" />
                <p>Getting your budget ready…</p>
              </div>
            ) : (
              <>
                {view === 'Overview' && forecast && (
                  <>
                    <div className="stats overview-stats">
                      <div className="stat">
                        <span className="stat-label">
                          <span className="stat-icon expense">
                            <ArrowUpRight size={17} />
                          </span>
                          Planned expenses
                        </span>
                        <strong>{fmt(forecast.expenses)}</strong>
                        <small>Bills + included purchases</small>
                      </div>
                      <div
                        className={
                          'stat balance ' + (forecast.deficit ? 'negative' : '')
                        }
                      >
                        <span className="stat-label">
                          <Leaf size={18} />
                          Room in your budget
                        </span>
                        <strong>{fmt(forecast.remaining)}</strong>
                        <small>
                          {forecast.deficit
                            ? 'A few adjustments could help.'
                            : 'A little breathing room.'}
                        </small>
                      </div>
                      <div className="stat">
                        <span className="stat-label">
                          <span className="stat-icon actual">
                            <ChartNoAxesCombined size={17} />
                          </span>
                          Actual spending
                        </span>
                        <strong>
                          {actualData ? fmt(actualData.actual.expenses) : '…'}
                        </strong>
                        <small>
                          {monthLabel(actualMonth, true)} ·{' '}
                          {actualData
                            ? `${actualData.actual.transaction_count} transactions · ${actualData.actual.status}`
                            : 'Loading…'}
                        </small>
                        <label
                          className="checkbox actual-month-toggle"
                          title="Checked uses the selected budget month; unchecked uses its previous month"
                        >
                          <input
                            type="checkbox"
                            checked={currentActual}
                            onChange={(e) => setCurrentActual(e.target.checked)}
                          />
                          Current month
                        </label>
                        <button
                          className="text-button stat-drill"
                          onClick={() => {
                            setSpendingMode('breakdown');
                            setView('Spending');
                          }}
                        >
                          Explore breakdown <ArrowRight size={13} />
                        </button>
                      </div>
                    </div>
                    <PlanningOverview
                      month={month}
                      onChanged={refresh}
                      currency={currency}
                      revision={revision}
                      onOpen={() => setView('Planning')}
                    />
                    {budgetAlerts.ready &&
                      forecast.deficit &&
                      !budgetAlerts.isDismissed('forecast_deficit', month) && (
                        <div
                          role="alert"
                          className="notice danger forecast-deficit"
                        >
                          <AlertTriangle size={18} />
                          <span>
                            Forecast expenses exceed income by{' '}
                            {fmt(-forecast.remaining)}.
                          </span>
                          {settings.advisor_enabled ? (
                            <button
                              className="text-button"
                              onClick={() => {
                                setAdvisorEntry({
                                  key: Date.now(),
                                  question: `Help me reconcile the ${monthLabel(month)} forecast deficit of ${fmt(-forecast.remaining)}. Compare it with ${monthLabel(shiftMonth(month, -1))}, explain what changed in income and expenses, and suggest realistic spending reductions to close the gap. Distinguish credit-card bills already owed from future flexible spending.`,
                                });
                                setView('Budget advisor');
                              }}
                            >
                              Reconcile with Budget advisor →
                            </button>
                          ) : (
                            <button
                              className="text-button"
                              onClick={() => setView('Settings')}
                            >
                              Set up Budget advisor →
                            </button>
                          )}
                          <button
                            className="text-button"
                            disabled={budgetAlerts.busy}
                            aria-label={`Dismiss forecast deficit alert for ${monthLabel(month)}`}
                            onClick={() =>
                              void budgetAlerts.dismiss(
                                'forecast_deficit',
                                month,
                              )
                            }
                          >
                            Dismiss
                          </button>
                        </div>
                      )}
                    {budgetAlerts.ready &&
                      actualData?.actual_deficit &&
                      !budgetAlerts.isDismissed(
                        'actual_deficit',
                        actualMonth,
                      ) && (
                        <div
                          role="alert"
                          className="notice danger actual-deficit"
                        >
                          <AlertTriangle size={18} />
                          <span>
                            Recorded spending for {monthLabel(actualMonth)}{' '}
                            exceeds that month’s forecast income by{' '}
                            {fmt(
                              actualData.actual.expenses - actualData.income,
                            )}
                            .
                          </span>
                          <button
                            className="text-button"
                            onClick={() => {
                              setSpendingMode('transactions');
                              setView('Spending');
                            }}
                          >
                            Review spending <ArrowRight size={15} />
                          </button>
                          <button
                            className="text-button"
                            disabled={budgetAlerts.busy}
                            aria-label={`Dismiss recorded spending alert for ${monthLabel(actualMonth)}`}
                            onClick={() =>
                              void budgetAlerts.dismiss(
                                'actual_deficit',
                                actualMonth,
                              )
                            }
                          >
                            Dismiss
                          </button>
                        </div>
                      )}
                    <div className="overview-grid">
                      <UpcomingBills
                        currency={currency}
                        categories={categories}
                        revision={revision}
                        onAdd={() => openRecurring()}
                        onEdit={(id) => {
                          const item = recurring.find((r) => r.id === id);
                          if (item) openRecurring(item);
                          else
                            setError(
                              'This recurring bill is no longer available. Refresh and try again.',
                            );
                        }}
                        onChanged={refresh}
                      />
                      <div className="overview-tools">
                        <OverviewComparison
                          currency={currency}
                          revision={revision}
                        />
                      </div>
                    </div>
                    <section className="panel year-panel">
                      <div className="section-head">
                        <div>
                          <h2>The bigger picture</h2>
                          <p>
                            Your forecast income and expenses across{' '}
                            {month.slice(0, 4)}.
                          </p>
                        </div>
                        <span className="legend">
                          <i />
                          Income <i className="sand" />
                          Expenses
                        </span>
                      </div>
                      <YearSummary
                        year={month.slice(0, 4)}
                        currency={currency}
                        revision={revision}
                        selectMonth={setMonth}
                      />
                    </section>
                  </>
                )}
                {view === 'Recurring accounts' && (
                  <>
                    <div className="recurring-summary-grid">
                      <section className="panel">
                        <div className="recurring-income-summary">
                          <div className="stat">
                            <span className="stat-label">
                              <span className="stat-icon income">
                                <ArrowDownLeft size={17} />
                              </span>
                              Monthly expected income
                            </span>
                            <strong>
                              {forecast && forecast.month === month
                                ? fmt(forecast.income)
                                : '…'}
                            </strong>
                            <small>{monthLabel(month)} · forecast income</small>
                          </div>
                        </div>
                      </section>
                    </div>
                    <AnnualExpectedIncome
                      year={Number(month.slice(0, 4))}
                      currency={currency}
                      revision={revision}
                      onChanged={refresh}
                    />
                    <section className="panel">
                      <div className="section-head">
                        <div>
                          <h2>Income & recurring bills</h2>
                          <p>
                            Adjust amounts by month without rewriting the past.
                          </p>
                        </div>
                        <button onClick={() => openRecurring()}>
                          <Plus size={17} />
                          Add account
                        </button>
                      </div>
                      {!recurring.length ? (
                        <Empty title="Give the regular things a home">
                          Add income, monthly bills, and annual expenses to see
                          your forecast.
                        </Empty>
                      ) : (
                        <div className="account-list">
                          {recurring.map((r) => (
                            <article className="account-row" key={r.id}>
                              <div className="row-top">
                                <span
                                  className={
                                    'category-icon ' +
                                    (r.kind === 'receivable' ? 'income' : '')
                                  }
                                >
                                  <Repeat2 size={20} />
                                </span>
                                <div className="grow">
                                  <h3>{r.name}</h3>
                                  <p>
                                    {r.kind === 'receivable'
                                      ? 'Income'
                                      : catName(r.category_id)}{' '}
                                    ·{' '}
                                    {r.frequency === 'annual' &&
                                    r.kind === 'payable'
                                      ? r.distribute_annual
                                        ? 'annual total, allocated monthly'
                                        : `annual total, ${r.due_day ? 'due' : 'forecast in'} ${new Date(2026, (r.due_month ?? Number(r.start_month.slice(5))) - 1, 2).toLocaleDateString(undefined, { month: 'long' })}`
                                      : r.frequency}{' '}
                                    · {r.start_month}
                                    {r.end_month
                                      ? ' → ' + r.end_month
                                      : ' onward'}
                                  </p>
                                  {r.kind === 'payable' &&
                                    !r.due_day &&
                                    !r.ach_enabled && (
                                      <small className="ach-label">
                                        Budget allowance · no due date or paid
                                        confirmation
                                      </small>
                                    )}
                                  {r.due_day && (
                                    <small className="ach-label">
                                      Due{' '}
                                      {r.frequency === 'annual'
                                        ? new Date(
                                            2026,
                                            (r.due_month ??
                                              Number(r.start_month.slice(5))) -
                                              1,
                                            2,
                                          ).toLocaleDateString(undefined, {
                                            month: 'long',
                                          }) + ' '
                                        : ''}
                                      {r.due_day}
                                      {r.frequency === 'monthly'
                                        ? ' each month'
                                        : ''}{' '}
                                      · tracking from {r.payment_tracking_start}
                                    </small>
                                  )}
                                  {r.ach_enabled && (
                                    <small className="ach-label">
                                      ACH auto-record · day {r.ach_day} ·{' '}
                                      {
                                        accounts.find(
                                          (a) => a.id === r.ach_account_id,
                                        )?.name
                                      }{' '}
                                      · from {r.ach_start_month}
                                    </small>
                                  )}
                                </div>
                                {r.kind === 'payable' &&
                                  r.frequency === 'annual' &&
                                  !!r.due_day && (
                                    <button
                                      className="secondary small"
                                      onClick={async () => {
                                        try {
                                          const plan = await api<PlanDraft>(
                                            `/planning/annual/${r.id}`,
                                            'POST',
                                          );
                                          setPlanDraft({
                                            key: Date.now(),
                                            value: plan,
                                          });
                                          refresh();
                                          setView('Planning');
                                        } catch (e) {
                                          setError((e as Error).message);
                                        }
                                      }}
                                    >
                                      Track in Planning
                                    </button>
                                  )}
                                <button
                                  className="secondary small"
                                  onClick={() => adjustRecurring(r)}
                                >
                                  Adjust amount
                                </button>
                                <button
                                  className="icon"
                                  aria-label={`Edit ${r.name}`}
                                  onClick={() => openRecurring(r)}
                                >
                                  <Pencil size={16} />
                                </button>
                                <button
                                  className="icon"
                                  aria-label={`Delete ${r.name}`}
                                  onClick={() =>
                                    remove('/recurring/' + r.id, r.name)
                                  }
                                >
                                  <Trash2 size={16} />
                                </button>
                              </div>
                              <details>
                                <summary>
                                  Amount history · {r.changes.length}{' '}
                                  {r.changes.length === 1 ? 'entry' : 'entries'}
                                </summary>
                                <div className="history">
                                  {r.changes.map((c) => (
                                    <div key={c.id}>
                                      <span>
                                        {c.month} ·{' '}
                                        {c.override
                                          ? 'This month only'
                                          : 'Ongoing default'}
                                      </span>
                                      <strong>
                                        {fmt(c.amount)}
                                        {r.frequency === 'annual'
                                          ? ' / year'
                                          : ''}
                                      </strong>
                                      {(c.override ||
                                        c.month !== r.start_month) && (
                                        <button
                                          className="icon"
                                          aria-label="Remove amount change"
                                          onClick={() =>
                                            remove(
                                              `/recurring/${r.id}/amount/${c.id}`,
                                              'this amount change',
                                            )
                                          }
                                        >
                                          <X size={14} />
                                        </button>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </details>
                            </article>
                          ))}
                        </div>
                      )}
                    </section>
                  </>
                )}
                {view === 'Planning' && (
                  <Planning
                    advisorEnabled={settings.advisor_enabled}
                    currency={currency}
                    revision={revision}
                    onChanged={refresh}
                    onDiscuss={(id) => {
                      if (!settings.advisor_enabled) {
                        setView('Settings');
                        return;
                      }
                      setAdvisorPlanId(id);
                      setView('Budget advisor');
                    }}
                    onDeleted={(id) => {
                      if (advisorPlanId === id) setAdvisorPlanId(null);
                    }}
                    initialDraft={planDraft}
                    onDraftUsed={() => setPlanDraft(null)}
                  />
                )}
                {view === 'Spending' && (
                  <>
                    <div
                      className="planning-mode spending-sections"
                      role="group"
                      aria-label="Spending section"
                    >
                      {(
                        [
                          ['breakdown', 'Expense breakdown'],
                          ['entries', 'All expense entries'],
                          ['transactions', 'Transactions'],
                          ['historical', 'Historical trends'],
                        ] as const
                      ).map(([value, label]) => (
                        <button
                          key={value}
                          className={
                            'chip ' + (spendingMode === value ? 'selected' : '')
                          }
                          aria-pressed={spendingMode === value}
                          onClick={() => setSpendingMode(value)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    {spendingMode !== 'historical' && (
                      <div hidden={spendingMode === 'transactions'}>
                        <ExpenseBreakdown
                          month={month}
                          actualMonth={actualMonth}
                          currentActual={currentActual}
                          onCurrentActualChange={setCurrentActual}
                          onMonthChange={(value, basis) =>
                            setMonth(
                              basis === 'actual' && !currentActual
                                ? shiftMonth(value, 1)
                                : value,
                            )
                          }
                          currency={currency}
                          revision={revision}
                          view={
                            spendingMode === 'entries' ? 'entries' : 'breakdown'
                          }
                          active={
                            spendingMode === 'breakdown' ||
                            spendingMode === 'entries'
                          }
                          onShowEntries={() => setSpendingMode('entries')}
                          onShowBreakdown={() => setSpendingMode('breakdown')}
                        />
                      </div>
                    )}
                    {spendingMode === 'transactions' && (
                      <section className="panel">
                        <div className="section-head">
                          <div>
                            <h2>Transactions</h2>
                            <p>
                              {monthLabel(actualMonth)} ·{' '}
                              {actualBusy
                                ? 'loading…'
                                : (actualData?.actual.status ?? 'unavailable')}
                            </p>
                          </div>
                          <div className="button-group">
                            <button
                              className="secondary"
                              aria-label="Refresh spending data"
                              disabled={loading || actualLoading}
                              onClick={refresh}
                            >
                              <RotateCcw
                                size={16}
                                className={actualLoading ? 'spin' : ''}
                              />
                              {actualLoading ? 'Refreshing…' : 'Refresh'}
                            </button>
                            <button onClick={() => openTransaction()}>
                              <Plus size={16} />
                              Add transaction
                            </button>
                          </div>
                        </div>
                        {transactionPage.error && (
                          <p role="alert">{transactionPage.error}</p>
                        )}
                        <div
                          className="button-group"
                          aria-label="Transaction pages"
                        >
                          <button
                            disabled={
                              !transactionPage.hasPrevious ||
                              transactionPage.loading
                            }
                            onClick={transactionPage.first}
                          >
                            First page
                          </button>
                          <button
                            disabled={
                              !transactionPage.next_cursor ||
                              transactionPage.loading
                            }
                            onClick={transactionPage.next}
                          >
                            Next page
                          </button>
                        </div>
                        <div className="transaction-toolbar">
                          <input
                            aria-label="Search transactions"
                            placeholder="Search descriptions…"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                          />
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={currentActual}
                              onChange={(e) =>
                                setCurrentActual(e.target.checked)
                              }
                            />
                            Current month
                          </label>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={currentActual}
                              onChange={(e) =>
                                setCurrentActual(e.target.checked)
                              }
                            />
                            Current month
                          </label>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={
                                actualData?.actual.marked_complete ?? false
                              }
                              disabled={actualBusy || !actualData}
                              onChange={(e) =>
                                void act(() =>
                                  api('/months/' + actualMonth, 'PUT', {
                                    complete: e.target.checked,
                                  }),
                                )
                              }
                            />
                            Actuals complete for this month
                          </label>
                        </div>
                        {!accounts.length && (
                          <div className="notice">
                            Add a card account in Settings before recording or
                            importing transactions.
                            <button
                              className="text-button"
                              onClick={() => setView('Settings')}
                            >
                              Open Settings <ArrowRight size={15} />
                            </button>
                          </div>
                        )}
                        {actualBusy ? (
                          <p className="muted pad" role="status">
                            Loading transactions…
                          </p>
                        ) : filteredTransactions.length ? (
                          <div className="table-scroll">
                            <table>
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Description</th>
                                  <th>Category</th>
                                  <th>Type</th>
                                  <th>Amount</th>
                                  <th>
                                    <span className="sr-only">Actions</span>
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {filteredTransactions.map((t) => (
                                  <tr key={t.id}>
                                    <td>{t.date}</td>
                                    <td>
                                      <strong>{t.description}</strong>
                                      <small>
                                        {
                                          accounts.find(
                                            (a) => a.id === t.account_id,
                                          )?.name
                                        }
                                      </small>
                                      {t.provenance?.type ===
                                        'scheduled_ach' && (
                                        <small className="ach-label">
                                          Scheduled ACH · confirm with bank
                                        </small>
                                      )}
                                    </td>
                                    <td>
                                      {t.category_id
                                        ? catName(t.category_id)
                                        : '—'}
                                    </td>
                                    <td>
                                      <span className="pill">{t.kind}</span>
                                    </td>
                                    <td
                                      className={
                                        t.kind === 'refund' ? 'green' : ''
                                      }
                                    >
                                      {t.kind === 'refund' ? '−' : ''}
                                      {fmt(t.amount)}
                                    </td>
                                    <td className="nowrap">
                                      <button
                                        className="icon"
                                        aria-label={`Edit ${t.description}`}
                                        onClick={() => openTransaction(t)}
                                      >
                                        <Pencil size={15} />
                                      </button>
                                      <button
                                        className="icon"
                                        aria-label={`Delete ${t.description}`}
                                        onClick={() =>
                                          remove(
                                            '/transactions/' + t.id,
                                            t.description,
                                          )
                                        }
                                      >
                                        <Trash2 size={15} />
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <Empty title="No transactions to show">
                            Import a statement or add a transaction. Payments
                            and transfers won’t count as spending.
                          </Empty>
                        )}
                      </section>
                    )}
                    {spendingMode === 'historical' && (
                      <Suspense
                        fallback={
                          <p role="status">Loading spending history…</p>
                        }
                      >
                        <HistoricalSpending
                          categories={categories}
                          currency={currency}
                          revision={revision}
                          historyEnd={historyEnd}
                          setHistoryEnd={setHistoryEnd}
                          selectedCats={selectedCats}
                          setSelectedCats={setSelectedCats}
                          overlay={overlay}
                          setOverlay={setOverlay}
                          drillMonth={drillMonth}
                          refresh={refresh}
                        />
                      </Suspense>
                    )}
                  </>
                )}
                {view === 'Statement imports' && (
                  <section className="panel statement-imports">
                    <div className="section-head">
                      <div>
                        <h2>Statement imports</h2>
                        <p>
                          {
                            imports.filter(
                              (j) =>
                                !['committed', 'undone'].includes(j.status),
                            ).length
                          }{' '}
                          awaiting review ·{' '}
                          {
                            imports.filter((j) => j.status === 'committed')
                              .length
                          }{' '}
                          saved
                        </p>
                      </div>
                      <button onClick={startImport}>
                        <Upload size={16} />
                        Import statements
                      </button>
                    </div>
                    {importPage.error && <p role="alert">{importPage.error}</p>}
                    <div
                      className="button-group pagination"
                      aria-label="Import pages"
                    >
                      <button
                        disabled={!importPage.hasPrevious || importPage.loading}
                        onClick={importPage.first}
                      >
                        First page
                      </button>
                      <button
                        disabled={!importPage.next_cursor || importPage.loading}
                        onClick={importPage.next}
                      >
                        Next page
                      </button>
                    </div>
                    {imports.length ? (
                      imports.map((j) => (
                        <button
                          className="import-item"
                          key={j.id}
                          onClick={() => void act(() => openImport(j.id))}
                        >
                          <Upload size={18} />
                          <span className="grow">
                            <strong>{j.filename}</strong>
                            <small>
                              {
                                accounts.find((a) => a.id === j.account_id)
                                  ?.name
                              }{' '}
                              · {j.period}
                            </small>
                          </span>
                          <span
                            className={
                              'pill ' +
                              (importStage(j.status).saved ? 'included' : '')
                            }
                          >
                            {importStage(j.status).label}
                          </span>
                          <span className="import-action">
                            {importStage(j.status).action}
                          </span>
                          <ChevronRight size={18} />
                        </button>
                      ))
                    ) : (
                      <Empty
                        title="Your statements start here"
                        action={
                          <button onClick={startImport}>
                            <Upload size={16} />
                            Choose statement files
                          </button>
                        }
                      >
                        Upload one or several CSV or text-PDF statements, then
                        review before saving. Column mappings are remembered for
                        each card.
                      </Empty>
                    )}
                  </section>
                )}
                {view === 'Settings' && (
                  <div className="settings-grid">
                    <div className="settings-column">
                      <PlanningCategories
                        revision={revision}
                        onChanged={refresh}
                      />
                      <section className="panel">
                        <div className="section-head">
                          <div>
                            <h2>Budget & optional local tools</h2>
                            <p>Your data stays in local PostgreSQL.</p>
                          </div>
                        </div>
                        <form
                          className="settings-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const data = new FormData(e.currentTarget);
                            void act(() =>
                              api('/settings', 'PUT', {
                                currency: data.get('currency'),
                                model: data.get('model'),
                                advisor_enabled:
                                  data.get('advisor_enabled') === 'on',
                                advisor_memory_enabled:
                                  data.get('advisor_memory_enabled') === 'on',
                              }),
                            );
                          }}
                        >
                          <label>
                            Budget currency
                            <select
                              name="currency"
                              defaultValue={currency}
                              key={currency}
                            >
                              {[
                                'USD',
                                'EUR',
                                'GBP',
                                'CAD',
                                'AUD',
                                'JPY',
                                'CHF',
                              ].map((c) => (
                                <option key={c}>{c}</option>
                              ))}
                            </select>
                            <small>
                              Currency is fixed once entries or imports exist.
                            </small>
                          </label>
                          <label>
                            Local model for advisor / PDF extraction
                            <select
                              name="model"
                              defaultValue={settings.model}
                              key={settings.model + models.models.join()}
                            >
                              <option value="">
                                None · CSV and manual review only
                              </option>
                              {[
                                ...new Set([
                                  ...models.models,
                                  ...(settings.model ? [settings.model] : []),
                                ]),
                              ].map((m) => (
                                <option key={m}>{m}</option>
                              ))}
                            </select>
                            <small>
                              Choose an installed model for chat or optional PDF
                              extraction. CSV categorization uses remembered
                              payees only.
                            </small>
                          </label>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              name="advisor_enabled"
                              defaultChecked={settings.advisor_enabled}
                              key={String(settings.advisor_enabled)}
                            />
                            Enable Budget advisor in the main menu
                          </label>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              name="advisor_memory_enabled"
                              defaultChecked={
                                settings.advisor_memory_enabled ?? false
                              }
                              key={
                                'memory' +
                                String(settings.advisor_memory_enabled)
                              }
                            />
                            Enable optional local advisor memory (Memora)
                          </label>
                          {models.error && (
                            <p className="notice">{models.error}</p>
                          )}
                          <div className="button-group">
                            <button>Save settings</button>
                            <button
                              type="button"
                              className="secondary"
                              onClick={() =>
                                void act(async () =>
                                  setModels(await api('/models')),
                                )
                              }
                            >
                              Refresh models
                            </button>
                          </div>
                        </form>
                      </section>
                      <AdvisorMemory
                        enabled={settings.advisor_memory_enabled ?? false}
                        revision={revision}
                      />
                      {budgetAlerts.count > 0 && (
                        <section className="panel">
                          <div className="section-head">
                            <div>
                              <h2>Dismissed budget alerts</h2>
                              <p>
                                {budgetAlerts.count} reviewed alerts stay hidden
                                by month and type, even if amounts change.
                              </p>
                            </div>
                          </div>
                          <div className="pad">
                            <button
                              className="secondary"
                              disabled={budgetAlerts.busy}
                              onClick={() => void budgetAlerts.restore()}
                            >
                              Restore dismissed alerts
                            </button>
                          </div>
                        </section>
                      )}
                    </div>
                    <div className="settings-column">
                      <section className="panel">
                        <div className="section-head">
                          <div>
                            <h2>Bank & card accounts</h2>
                            <p>
                              Add a bank account for ACH debits or a card for
                              statement imports. Check a card to show in-app
                              alerts when information is over 30 days old.
                            </p>
                          </div>
                          <button
                            className="text-button"
                            onClick={() => manageName('accounts')}
                          >
                            <Plus size={16} />
                            Add
                          </button>
                        </div>
                        {accounts.map((a) => (
                          <div className="name-row" key={a.id}>
                            <div className="grow">
                              <strong>{a.name}</strong>
                              <small>
                                {a.last_information_date
                                  ? `Information through ${a.last_information_date}`
                                  : 'No saved information yet'}
                              </small>
                              {a.csv_mapping && (
                                <small>CSV mapping remembered</small>
                              )}
                            </div>
                            <label className="checkbox card-monitor">
                              <input
                                type="checkbox"
                                checked={a.stale_alert_enabled}
                                disabled={monitoring !== null}
                                onChange={(e) =>
                                  void monitorCard(a.id, e.target.checked)
                                }
                                aria-label={`Alert when ${a.name} information is over 30 days old`}
                              />
                              Alert after 30 days
                            </label>
                            <button
                              className="icon"
                              aria-label={`Edit ${a.name}`}
                              onClick={() => manageName('accounts', a)}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              className="icon"
                              aria-label={`Delete ${a.name}`}
                              onClick={() =>
                                remove('/accounts/' + a.id, a.name)
                              }
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        ))}
                        {!accounts.length && (
                          <p className="muted pad">
                            Add a named card to start tracking actual spending.
                          </p>
                        )}
                      </section>
                      <section className="panel">
                        <div className="section-head">
                          <div>
                            <h2>Categories</h2>
                            <p>Make these feel like you.</p>
                          </div>
                          <button
                            className="text-button"
                            onClick={() => manageName('categories')}
                          >
                            <Plus size={16} />
                            Add
                          </button>
                        </div>
                        {categories.map((c, i) => (
                          <div className="name-row" key={c.id}>
                            <i
                              className="color-dot"
                              style={{ background: colors[i % colors.length] }}
                            />
                            <strong>{c.name}</strong>
                            <button
                              className="icon"
                              aria-label={`Edit ${c.name}`}
                              onClick={() => manageName('categories', c)}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              className="icon"
                              aria-label={`Delete ${c.name}`}
                              onClick={() =>
                                remove('/categories/' + c.id, c.name)
                              }
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        ))}
                      </section>
                      <RememberedPayees
                        categories={categories}
                        model={settings.model}
                        revision={revision}
                        onChanged={refresh}
                      />
                      <div className="quiet-note">
                        <Leaf size={22} />
                        <h3>A private little workspace.</h3>
                        <p>
                          No bank connections, no cloud model fallback, and no
                          notifications outside the app. Back up your PostgreSQL
                          database to keep your budget safe.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
            {settings.advisor_enabled &&
              (view === 'Budget advisor' || advisorVisited) && (
                <div hidden={view !== 'Budget advisor'}>
                  <BudgetAdvisor
                    entry={advisorEntry}
                    planId={advisorPlanId}
                    onClearPlan={() => setAdvisorPlanId(null)}
                    onCreatePlan={(value) => {
                      setPlanDraft({ key: Date.now(), value });
                      setView('Planning');
                    }}
                    revision={revision}
                    month={month}
                    currency={currency}
                    model={settings.model}
                    memoryEnabled={settings.advisor_memory_enabled ?? false}
                  />
                </div>
              )}
            <footer>
              Made for a little peace of mind.
              <span>
                <span className="status-dot" />
                One month at a time.
              </span>
            </footer>
          </div>
        </main>
        {editor && (
          <FormEditor
            editor={editor}
            onClose={() => setEditor(null)}
            onSaved={refresh}
          />
        )}
        {uploading && (
          <BatchUploadDialog
            latestReview={importUpdate}
            accounts={accounts}
            month={uploadPeriod ?? actualMonth}
            initialAccount={uploadAccount}
            onClose={() => setUploading(false)}
            onPrepared={refresh}
            onReview={(j, closeQueue) => {
              setImportJob(j);
              if (closeQueue) setUploading(false);
              refresh();
            }}
          />
        )}
        {importJob && (
          <ImportReview
            initial={importJob}
            categories={categories}
            currency={currency}
            onClose={() => {
              setImportJob(null);
              refresh();
            }}
            onChanged={(update) => {
              if (update)
                setImportUpdate({ id: update.id, status: update.status });
              refresh();
            }}
          />
        )}
      </div>
    </Suspense>
  );
}
