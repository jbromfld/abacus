export type Category = { id: string; name: string };
export type Account = Category & {
  stale_alert_enabled: boolean;
  csv_mapping: Record<string, string | null> | null;
  last_information_date: string | null;
  days_since_update: number | null;
  stale: boolean;
};
export type PayeeRule = {
  id: string;
  payee: string;
  kind: string;
  category_id: string;
};
export type Settings = {
  currency: string;
  model: string;
  advisor_enabled: boolean;
  reserve_alerts_enabled: boolean;
  reserve_checkpoint_day: number;
};
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
export type Purchase = {
  id: string;
  name: string;
  amount: number;
  month: string;
  category_id: string;
  notes: string;
  included: boolean;
};
export type Transaction = {
  id: string;
  date: string;
  description: string;
  amount: number;
  kind: string;
  category_id: string | null;
  account_id: string;
  import_id?: string;
  provenance?: { type?: string };
};
export type Forecast = {
  month: string;
  income: number;
  expenses: number;
  remaining: number;
  deficit: boolean;
  actual_deficit: boolean;
  actual: {
    expenses: number;
    status: string;
    marked_complete: boolean;
    transaction_count: number;
  };
  lines: {
    id: string;
    name: string;
    kind: string;
    amount: number;
    category_id: string | null;
  }[];
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
export type ImportSummary = {
  id: string;
  filename: string;
  period: string;
  status: string;
  account_id: string;
  error: string;
};
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
export async function api<T>(
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
  });
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
  return response.json() as Promise<T>;
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
export type BillEstimate = MonthlyBillScenario & {
  id: string;
  category_id: string;
  due_day: number | null;
  included: boolean;
  recurring_id: string | null;
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
  estimate_id?: string;
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

export type ReserveCheck = {
  today: string;
  enabled: boolean;
  checkpoint_day: number;
  eligible_bill_count: number;
  status:
    | 'no_bills'
    | 'not_configured'
    | 'needs_update'
    | 'below_target'
    | 'payment_risk'
    | 'on_track'
    | 'scheduled';
  dismissed: boolean;
  plan: null | {
    amount: number;
    start_date: string;
    schedules: {
      name: string;
      start_month: string;
      end_month: string | null;
      due_day: number;
      due_month: number;
      changes: { month: string; amount: number; override: boolean }[];
    }[];
    schedule_changed: boolean;
    dismissed_until: string | null;
  };
  observations: { amount: number; as_of: string }[];
  latest?: { amount: number; as_of: string } | null;
  checkpoint?: string | null;
  next_checkpoint?: string;
  target?: number;
  target_as_of?: string;
  next_target?: number;
  fresh?: boolean;
  shortfall?: number | null;
  upcoming?: {
    due_date: string;
    bills: { name: string; amount: number }[];
    amount: number;
    projected_before_payment: number | null;
    shortfall: number | null;
    assumes_future_allocations: boolean;
  }[];
  checkpoints?: {
    date: string;
    target: number;
    allocation: number;
    allocations: { name: string; amount: number }[];
    allocations_to_date: number;
    payments_to_date: number;
  }[];
};
