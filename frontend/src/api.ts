import type * as Contract from './generated/api';
import { sharedRead, invalidateResources } from './resourceCache';
export type Category = Pick<Contract.CategoryOut, 'id' | 'name'>;
export type Account = Contract.AccountOut;
export type PayeeRule = {
  id: string;
  payee: string;
  kind: string;
  category_id: string;
};
export type Settings = Pick<
  Contract.SettingsOut,
  'currency' | 'model' | 'advisor_enabled' | 'advisor_memory_enabled'
>;
export type Change = {
  id: string;
  month: string;
  amount: number;
  override: boolean;
};
export type Recurring = {
  id: string;
  name: string;
  kind: 'payable' | 'receivable';
  frequency: 'monthly' | 'annual';
  distribute_annual: boolean;
  category_id: string | null;
  start_month: string;
  end_month: string | null;
  due_day: number | null;
  due_month: number | null;
  payment_tracking_start: string | null;
  ach_enabled: boolean;
  ach_day: number | null;
  ach_start_month: string | null;
  ach_account_id: string | null;
  changes: Change[];
};
export type Transaction = Omit<Contract.TransactionOut, 'import_id'> & {
  import_id?: string | null;
};
export type Forecast = Contract.ForecastOut;
export type SavingsAwareForecast = Forecast & {
  savings_balance: number | null;
  remaining_with_savings: number | null;
  projected_savings?: number | null;
  cash_expenses?: number | null;
  funding_gap?: number;
  projection_basis?: string;
  income_complete?: boolean;
  savings_adjusted_deficit: boolean;
};

export type Trend = {
  month: string;
  forecast: number;
  income: number;
  actual: number | null;
  status: string;
  categories: Record<string, { actual: number | null; forecast: number }>;
};
export type ReviewRow = {
  date: string;
  description: string;
  amount: number;
  kind: string;
  category_id: string | null;
  selected: boolean;
  errors: string[];
  duplicate?: boolean;
  skip_duplicate?: boolean;
  source?: Record<string, unknown>;
  source_index?: number;
  classification?: string | null;
};
export type ImportSummary = Contract.ImportSummaryOut;
export type ImportJob = ImportSummary & {
  commit_summary?: { added: number; skipped: number } | null;
  rows: ReviewRow[];
  source: {
    type: string;
    headers: string[];
    preview: Record<string, string>[];
    mapping?: Record<string, string | null>;
    mapping_warning?: string | null;
  };
};
function connectionFailure(error: unknown, signal?: AbortSignal): never {
  if (signal?.aborted || (error as Error)?.name === 'AbortError') throw error;
  throw Object.assign(
    new Error(
      'Connection to Abacus was interrupted. The local server may be restarting. Wait a moment, then try again.',
    ),
    { status: 0, cause: error },
  );
}
async function request<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    signal,
    headers:
      body instanceof FormData
        ? {}
        : body === undefined
          ? {}
          : { 'Content-Type': 'application/json' },
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  }).catch((error: unknown) => connectionFailure(error, signal));
  if (!response.ok) {
    const data = await response.json().catch(() => ({
      detail: 'Unable to connect. Check that the Python server is running.',
    }));
    throw Object.assign(
      new Error(
        typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail),
      ),
      { status: response.status },
    );
  }
  return response.json().catch((error: unknown) => {
    if (error instanceof TypeError || (error as Error)?.name === 'AbortError')
      connectionFailure(error, signal);
    throw error;
  }) as Promise<T>;
}
export function monthNow() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
export function shiftMonth(month: string, n: number) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(y, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
export function actualMonthFor(budgetMonth: string, currentMonth = false) {
  return currentMonth ? budgetMonth : shiftMonth(budgetMonth, -1);
}
export function monthLabel(month: string, short = false) {
  return new Date(month + '-02T12:00:00').toLocaleDateString(undefined, {
    month: short ? 'short' : 'long',
    year: 'numeric',
  });
}
export function digits(currency: string) {
  return currency === 'JPY' ? 0 : 2;
}
export function money(amount: number, currency: string) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: digits(currency),
  }).format(amount / 10 ** digits(currency));
}
export function inputAmount(amount: number, currency: string) {
  return (amount / 10 ** digits(currency)).toFixed(digits(currency));
}
export function minor(value: string, currency: string) {
  if (
    !(digits(currency) === 0
      ? /^\d+$/.test(value)
      : /^\d+(?:\.\d{1,2})?$/.test(value))
  )
    throw new Error('Enter a positive amount with valid currency precision.');
  const n = Math.round(Number(value) * 10 ** digits(currency));
  if (!Number.isSafeInteger(n) || n <= 0)
    throw new Error('Enter a positive amount.');
  return n;
}

export type ImportUpdate = { id: string; status: string };
export async function loadImport(id: string): Promise<ImportJob> {
  const job = await api<ImportJob>('/imports/' + id);
  if (
    job.source.type === 'csv' &&
    !job.source.mapping &&
    ['prepared', 'review', 'failed', 'interrupted'].includes(job.status)
  )
    return api<ImportJob>(`/imports/${id}/mapping/default`, 'POST');
  return job;
}

export type BillOccurrence = {
  recurring_id: string;
  period: string;
  name: string;
  category_id: string | null;
  due_date: string;
  amount: number;
  paid: boolean;
  paid_on: string | null;
  confirmed_due_date: string | null;
  ach_recorded: boolean;
  automatic: boolean;
  paid_source: 'ach' | 'manual' | null;
  status: 'paid' | 'overdue' | 'today' | 'upcoming' | 'automatic';
};
export type AnnualBill = {
  recurring_id: string;
  name: string;
  category_id: string | null;
  distribute_annual: boolean;
  missing_due_date: boolean;
  allowance: boolean;
  annual_amount: number;
  monthly_allocation: number | null;
  next: BillOccurrence | null;
  overdue: BillOccurrence[];
  overdue_count: number;
};
export type DueSummary = {
  today: string;
  through: string;
  monthly_upcoming: BillOccurrence[];
  monthly_overdue: BillOccurrence[];
  annual: AnnualBill[];
  paid_history: BillOccurrence[];
};

export type SavingsInputs = { amount: number; month: string; floor: number };
export type SavingsSnapshot = {
  amount: number | null;
  month: string;
  floor: number;
};
export type MonthlyBillScenario = {
  name: string;
  amount: number;
  start_month: string;
  end_month: string | null;
};
export type SavingsPoint = {
  month: string;
  income: number;
  income_recorded: boolean;
  forecast_expenses: number;
  forecast_remaining: number;
  scenario_forecast_expenses: number;
  cash_expenses: number;
  distributed_allocation_removed: number;
  annual_payments: { name: string; amount: number }[];
  extra_bill: number;
  budget_remaining_after_bill: number;
  cash_remaining_after_bill: number;
  baseline_savings: number | null;
  scenario_savings: number | null;
};
export type SavingsProjection = {
  currency: string;
  starting_savings: number | null;
  savings_known: boolean;
  start_month: string;
  savings_floor: number;
  horizon_months: number;
  bill: (MonthlyBillScenario & { already_included: boolean }) | null;
  status:
    | 'missing_income'
    | 'outside_horizon'
    | 'negative_savings'
    | 'below_floor'
    | 'uses_savings'
    | 'fits'
    | 'budget_only';
  income_complete: boolean;
  missing_income_months: string[];
  ending_savings: number | null;
  baseline_ending_savings: number | null;
  total_new_bill_cost: number;
  lowest_savings: number | null;
  lowest_month: string | null;
  first_negative_month: string | null;
  first_below_floor_month: string | null;
  budget_deficit_months: string[];
  first_bill_month_remaining: number | null;
  first_active_month: string | null;
  total_budget_change: number;
  recurring_change: {
    name: string;
    frequency: string;
    action: string;
    start_month: string;
    end_month: string | null;
    amount: number | null;
  } | null;
  assumptions: string[];
  months: SavingsPoint[];
  bill_inferred_from_question?: boolean;
};
export type AdvisorBillPlan = {
  savings: SavingsInputs;
  bill?: MonthlyBillScenario;
  question: string;
};
export function nonnegativeMinor(value: string, currency: string) {
  const pattern = digits(currency) === 0 ? /^0+$/ : /^0+(?:\.0{1,2})?$/;
  return pattern.test(value.trim()) ? 0 : minor(value.trim(), currency);
}

export type CategoryAverage = {
  id: string;
  name: string;
  average: number | null;
  suggested_guide: number | null;
  monthly_guide: number | null;
  sample_count: number;
  partial_month_count: number;
};
export type SpendingAverages = {
  window_start: string;
  window_end: string;
  sample_count: number;
  partial_month_count: number;
  included_months: string[];
  excluded_months: string[];
  average: number | null;
  categories: CategoryAverage[];
  basis: string;
};

export type AdvisorSpendingComparison = {
  months: number;
  from_month: string;
  to_month: string;
  first_month_minor: number | null;
  last_month_minor: number | null;
  change_minor: number | null;
  partial_month_count: number;
  missing_month_count: number;
};
export type AdvisorSpendingHistory = {
  start_month: string;
  end_month: string;
  months: { month: string; status: string }[];
  basis: string;
  categories: {
    category: string;
    monthly_net_minor: (number | null)[];
    comparisons: AdvisorSpendingComparison[];
  }[];
  payees: {
    payee: string;
    category: string;
    monthly_net_minor: (number | null)[];
    comparisons: AdvisorSpendingComparison[];
  }[];
  payee_limit: number;
  additional_payees_omitted: number;
  payee_selection: string;
};

export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const cacheable =
    /^\/(settings|categories|accounts|recurring|forecast|forecasts|trends|spending|expenses|planning|savings)(?:[/?]|$)/.test(
      path,
    ) && !path.startsWith('/planning/draft');
  if (method === 'GET' && cacheable)
    return sharedRead(path, signal, (owned) =>
      request<T>(path, method, body, owned),
    );
  if (method !== 'GET') invalidateResources(path, false);
  try {
    return await request<T>(path, method, body, signal);
  } finally {
    if (method !== 'GET') invalidateResources(path);
  }
}
