import { useEffect, useRef, useState } from 'react';
import {
  MessageCircle,
  Send,
  RotateCcw,
  LoaderCircle,
  Leaf,
  AlertTriangle,
  Globe,
  ExternalLink,
} from 'lucide-react';
import { api, minor, money, monthLabel, inputAmount } from './api';
import type {
  Purchase,
  AdvisorBillPlan,
  SavingsInputs,
  SavingsProjection,
  BillEstimate,
} from './api';

type Research = {
  status: string;
  provider: string;
  queries: string[];
  missing_details: string[];
  warnings: string[];
  sources: {
    id: string;
    title: string;
    url: string;
    snippet: string;
    retrieved_at: string;
  }[];
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  research?: Research;
};
type Context = {
  currency: string;
  selected_month: string;
  current_date: string;
  savings_projection?: SavingsProjection | null;
  forecast_comparison: {
    previous_month: string;
    month: string;
    previous: {
      income_minor: number;
      expenses_minor: number;
      remaining_minor: number;
      income_recorded: boolean;
    };
    current: {
      income_minor: number;
      expenses_minor: number;
      remaining_minor: number;
      income_recorded: boolean;
    };
    remaining_change_minor: number;
    shortfall_minor: number;
    changes: {
      name: string;
      kind: string;
      category: string | null;
      source: string;
      frequency: string | null;
      annual_distributed: boolean | null;
      change: string;
      previous_minor: number;
      current_minor: number;
      delta_minor: number;
      remaining_impact_minor: number;
    }[];
  };
  web_research?: Research;
  planning_capacity: {
    available_savings_minor: number | null;
    monthly_buffer_minor: number | null;
    assumptions_complete: boolean;
    basis: string;
    earliest_funded_month_for_selected_scenario: string | null;
    buffer_shortfall_months: string[];
    months: {
      month: string;
      forecast_remaining_minor: number;
      potential_contribution_minor: number | null;
      hypothetical_trip_fund_minor: number | null;
    }[];
  };
  monthly_forecasts: {
    month: string;
    income_minor: number;
    expenses_minor: number;
    remaining_minor: number;
    income_entries: number;
  }[];
  recent_actuals: {
    month: string;
    status: string;
    total_spending_minor: number | null;
    categories: { name: string; spending_minor: number }[];
  }[];
  draft_purchases: { name: string; month: string; amount_minor: number }[];
  additional_drafts_omitted: number;
  purchase_scenario: null | {
    name: string;
    month: string;
    amount_minor: number;
    already_included: boolean;
    baseline_remaining_minor: number;
    remaining_after_purchase_minor: number;
    would_exceed_forecast: boolean;
  };
};
type Reply = { reply: string; context: Context };

export default function BudgetAdvisor({
  entry,
  month,
  currency,
  purchases,
  model,
  billPlan,
  revision,
  onOpenPlanner,
}: {
  entry: { question: string; key: number } | null;
  onOpenPlanner: () => void;
  month: string;
  currency: string;
  purchases: Purchase[];
  model: string;
  billPlan: AdvisorBillPlan | null;
  revision: number;
}) {
  const researchPreference = useRef<boolean | null>(null);
  const [webStatus, setWebStatus] = useState({
    provider: 'brave',
    available: false,
    message: '',
  });
  const [useWeb, setUseWeb] = useState(false);
  const [researchTopic, setResearchTopic] = useState('');
  const [savings, setSavings] = useState('');
  const [buffer, setBuffer] = useState('');
  const refreshWeb = () =>
    api<typeof webStatus>('/advisor/research-status')
      .then((status) => {
        setWebStatus(status);
        setUseWeb(researchPreference.current ?? false);
      })
      .catch((e) => setError((e as Error).message));
  const [researchPreview, setResearchPreview] = useState<{
    topic: string;
    queries: string[];
    missing_details: string[];
    confirmation: string;
  } | null>(null);
  const [researchConfirmed, setResearchConfirmed] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const previewResearch = async () => {
    const topic = researchTopic.trim();
    setResearchTopic(topic);
    setPreviewing(true);
    setError('');
    setResearchPreview(null);
    setResearchConfirmed(false);
    try {
      setResearchPreview(
        await api('/advisor/research-preview', 'POST', {
          topic,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPreviewing(false);
    }
  };
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [choice, setChoice] = useState('');
  const [monthlyAmount, setMonthlyAmount] = useState('');
  const [monthlyStart, setMonthlyStart] = useState(month);
  const [monthlyEnd, setMonthlyEnd] = useState('');
  const [handoffSavings, setHandoffSavings] = useState<SavingsInputs | null>(
    null,
  );
  const [billEstimates, setBillEstimates] = useState<BillEstimate[]>([]);
  useEffect(() => {
    let active = true;
    api<BillEstimate[]>('/bill-estimates')
      .then((items) => active && setBillEstimates(items))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [revision]);
  const [context, setContext] = useState<Context | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    setElapsed(0);
    if (!busy) return;
    const started = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [busy]);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const pendingId = useRef(0);
  useEffect(() => {
    void refreshWeb();
  }, []);
  const reset = () => {
    pendingId.current++;
    request.current?.abort();
    setMessages([]);
    setContext(null);
    setError('');
    setBusy(false);
  };
  useEffect(() => {
    reset();
    setQuestion('');
    setChoice('');
    setMonthlyStart(month);
    setHandoffSavings(null);
    return () => {
      pendingId.current++;
      request.current?.abort();
    };
  }, [month, currency, model]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' });
  }, [messages, busy, error]);
  useEffect(() => {
    if (!billPlan) return;
    reset();
    setQuestion(billPlan.question);
    setChoice(
      billPlan.estimate_id ? 'bill:' + billPlan.estimate_id : 'monthly-bill',
    );
    setMonthlyAmount(
      billPlan.bill ? inputAmount(billPlan.bill.amount, currency) : '',
    );
    setMonthlyStart(billPlan.bill?.start_month ?? month);
    setMonthlyEnd(billPlan.bill?.end_month ?? '');
    setHandoffSavings(billPlan.savings);
  }, [billPlan]);
  useEffect(() => {
    if (!entry) return;
    reset();
    setQuestion(entry.question);
    setChoice('');
    setHandoffSavings(null);
    researchPreference.current = false;
    setUseWeb(false);
    setResearchTopic('');
    requestAnimationFrame(() =>
      document.getElementById('advisor-question')?.focus(),
    );
  }, [entry]);
  const fmt = (n: number | null) =>
    n === null ? 'Unknown' : money(n, currency);
  const send = async () => {
    const text = question.trim();
    if (!text || busy) return;
    if (
      useWeb &&
      (!researchConfirmed ||
        !researchPreview?.queries.length ||
        researchPreview.topic !== researchTopic)
    ) {
      setError(
        'Preview and confirm the public search terms before asking with web research.',
      );
      return;
    }
    let planning;
    let monthlyBill;
    const optionalMoney = (v: string) =>
      v.trim() === '' ? null : Number(v) === 0 ? 0 : minor(v, currency);
    try {
      planning = {
        available_savings: optionalMoney(savings),
        monthly_buffer: optionalMoney(buffer),
      };
      if (choice === 'monthly-bill')
        monthlyBill = {
          name: 'Potential monthly bill',
          amount: minor(monthlyAmount, currency),
          start_month: monthlyStart,
          end_month: monthlyEnd || null,
        };
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    const history = messages
      .slice(-12)
      .map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }));
    const controller = new AbortController();
    request.current = controller;
    const id = ++pendingId.current;
    setBusy(true);
    setError('');
    setMessages([...messages, { role: 'user', content: text }]);
    setQuestion('');
    try {
      const result = await api<Reply>(
        '/advisor/chat',
        'POST',
        {
          month,
          message: text,
          history,
          use_web: useWeb,
          research_topic: researchTopic,
          research_confirmation: useWeb
            ? researchPreview?.confirmation
            : undefined,
          planning,
          purchase_id:
            choice &&
            choice !== 'custom' &&
            choice !== 'monthly-bill' &&
            !choice.startsWith('bill:')
              ? choice
              : null,
          monthly_bill: monthlyBill,
          bill_estimate_id: choice.startsWith('bill:') ? choice.slice(5) : null,
          savings:
            choice === 'monthly-bill' || choice.startsWith('bill:')
              ? handoffSavings
              : null,
        },
        controller.signal,
      );
      if (id !== pendingId.current) return;
      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: result.reply,
          research: result.context.web_research,
        },
      ]);
      setContext(result.context);
    } catch (e) {
      if (id !== pendingId.current) return;
      setMessages(messages);
      setQuestion(text);
      if ((e as Error).name !== 'AbortError') setError((e as Error).message);
    } finally {
      if (id === pendingId.current) setBusy(false);
    }
  };
  return (
    <div className="advisor-layout">
      <section className="panel advisor-chat">
        <div className="section-head">
          <div>
            <h2>
              <MessageCircle size={18} />
              Budget advisor
            </h2>
            <p>Think through a purchase, or look ahead together.</p>
          </div>
          <button
            className="text-button"
            onClick={reset}
            disabled={!messages.length && !busy}
          >
            <RotateCcw size={15} />
            New conversation
          </button>
        </div>
        <div
          className="chat-messages"
          role="log"
          aria-live="polite"
          aria-label="Budget conversation"
        >
          {!messages.length && !busy && (
            <div className="advisor-welcome">
              <div className="empty-icon">
                <Leaf size={25} />
              </div>
              <h3>A little perspective before you decide.</h3>
              <p>
                Ask about your plans using your budget’s recorded income,
                expenses, and estimates.
              </p>
              <div className="suggestions">
                {[
                  'Can I make this purchase without exceeding my budget?',
                  'Plan a Friday–Sunday trip to western New York in July 2027, including lodging and meals.',
                  'What kind of Puerto Vallarta weekend next fall would fit my budget?',
                ].map((q) => (
                  <button
                    key={q}
                    className="secondary"
                    onClick={() => setQuestion(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <article key={i} className={'chat-message ' + m.role}>
              <span>{m.role === 'user' ? 'You' : 'Budget advisor'}</span>
              <p>
                {m.content.split(/(\[S\d+\])/g).map((part, j) => {
                  const source = m.research?.sources.find(
                    (source) => '[' + source.id + ']' === part,
                  );
                  return source ? (
                    <a
                      key={j}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {part}
                    </a>
                  ) : (
                    part
                  );
                })}
              </p>
              {m.research && m.research.status !== 'disabled' && (
                <div className="research-results">
                  <small>Web research · {m.research.status}</small>
                  {m.research.warnings.map((warning, j) => (
                    <p className="research-warning" key={j}>
                      {warning}
                    </p>
                  ))}
                  {m.research.missing_details.length > 0 && (
                    <details open>
                      <summary>Details to confirm</summary>
                      <ul>
                        {m.research.missing_details.map((detail, j) => (
                          <li key={j}>{detail}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {m.research.sources.map((source) => (
                    <a
                      className="source-link"
                      key={source.id}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span>
                        [{source.id}] {source.title}
                      </span>
                      <ExternalLink size={12} />
                      <small>
                        {new URL(source.url).hostname} · retrieved{' '}
                        {new Date(source.retrieved_at).toLocaleDateString()}
                      </small>
                    </a>
                  ))}
                  {m.research.queries.length > 0 && (
                    <details>
                      <summary>Search terms sent to Brave</summary>
                      {m.research.queries.map((q, j) => (
                        <small key={j}>{q}</small>
                      ))}
                    </details>
                  )}
                </div>
              )}
            </article>
          ))}
          {busy && (
            <div className="chat-thinking" role="status">
              <LoaderCircle className="spin" size={16} />
              <span>
                {useWeb
                  ? 'Researching sources and considering your budget…'
                  : 'Thinking locally…'}{' '}
                {elapsed}s
                {elapsed >= 60 && (
                  <small>
                    Local models can take several minutes, especially while
                    loading.
                  </small>
                )}
              </span>
              <button
                className="text-button"
                onClick={() => {
                  pendingId.current++;
                  request.current?.abort();
                  setBusy(false);
                  setMessages(messages.slice(0, -1));
                  setQuestion(messages.at(-1)?.content ?? '');
                }}
              >
                Cancel
              </button>
            </div>
          )}
          {error && (
            <div className="notice danger" role="alert">
              <AlertTriangle size={17} />
              {error}
            </div>
          )}
          <div ref={end} />
        </div>
        <form
          className="chat-compose"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label htmlFor="advisor-question" className="sr-only">
            Ask about your budget
          </label>
          <textarea
            id="advisor-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={2000}
            placeholder="Would this purchase fit my budget over the next few months?"
            disabled={busy}
            required
          />
          <div>
            <small>
              Local model · {model}
              {useWeb ? ' · Brave web research' : ''}
              <br />
              Guidance based on forecasts. Your budget stays unchanged.
            </small>
            <button disabled={busy || !question.trim()}>
              <Send size={15} />
              Ask
            </button>
          </div>
        </form>
      </section>
      <aside className="advisor-side">
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>
                <Globe size={17} />
                Travel research
              </h2>
              <p>Sources, options, and a plan to fund it.</p>
            </div>
          </div>
          <div className="advisor-controls">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={useWeb}
                disabled={busy || !webStatus.available}
                onChange={(e) => {
                  researchPreference.current = e.target.checked;
                  setUseWeb(e.target.checked);
                }}
              />
              Use current web research
            </label>
            {!webStatus.available && (
              <p className="muted">
                {webStatus.message || 'Checking web research configuration…'}{' '}
                <button
                  className="text-button"
                  onClick={() => void refreshWeb()}
                >
                  Refresh connection
                </button>
              </p>
            )}
            <label>
              Public research topic (required for web research)
              <input
                value={researchTopic}
                maxLength={1000}
                disabled={busy}
                onChange={(e) => {
                  setResearchTopic(e.target.value);
                  setResearchPreview(null);
                  setResearchConfirmed(false);
                }}
                placeholder="Puerto Vallarta, fall 2027, weekend, flights from Detroit"
              />
              <small>
                Only this public topic is used for searches. Keep financial and
                identity details in the private chat. Preview and confirm the
                exact searches before sending them to Brave.
              </small>
            </label>
            {useWeb && (
              <div className="research-preview">
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || previewing || !researchTopic.trim()}
                  onClick={() => void previewResearch()}
                >
                  {previewing ? 'Preparing…' : 'Preview public searches'}
                </button>
                {researchPreview && (
                  <>
                    <ul>
                      {researchPreview.queries.map((q) => (
                        <li key={q}>{q}</li>
                      ))}
                    </ul>
                    {researchPreview.missing_details.map((d) => (
                      <p className="muted" key={d}>
                        {d}
                      </p>
                    ))}
                    {researchPreview.queries.length > 0 && (
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={researchConfirmed}
                          disabled={busy}
                          onChange={(e) =>
                            setResearchConfirmed(e.target.checked)
                          }
                        />
                        I approve sending these search terms to Brave.
                      </label>
                    )}
                  </>
                )}
              </div>
            )}
            <label>
              Funds already set aside ({currency}, optional)
              <input
                type="number"
                min="0"
                step={currency === 'JPY' ? '1' : '0.01'}
                value={savings}
                disabled={busy}
                onChange={(e) => setSavings(e.target.value)}
              />
            </label>
            <label>
              Monthly breathing room to preserve ({currency}, optional)
              <input
                type="number"
                min="0"
                step={currency === 'JPY' ? '1' : '0.01'}
                value={buffer}
                disabled={busy}
                onChange={(e) => setBuffer(e.target.value)}
              />
              <small>
                Without both amounts, the advisor asks before estimating a
                comfortable payment timeline.
              </small>
            </label>
          </div>
        </section>
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Planner context</h2>
              <p>Create and edit estimates in Purchase planner.</p>
            </div>
          </div>
          <div className="advisor-controls">
            <label>
              Saved planning context
              <select
                value={choice}
                disabled={busy}
                onChange={(e) => {
                  setChoice(e.target.value);
                  setHandoffSavings(null);
                  setContext(null);
                }}
              >
                <option value="">General budget question</option>
                {billPlan?.bill && (
                  <option value="monthly-bill">
                    Current Purchase planner preview
                  </option>
                )}
                {billEstimates.map((e) => (
                  <option key={e.id} value={'bill:' + e.id}>
                    {e.name} · {fmt(e.amount)}/month ·{' '}
                    {e.included ? 'added' : 'draft'}
                  </option>
                ))}
                {purchases.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {fmt(p.amount)} ·{' '}
                    {p.included ? 'included' : 'draft'}
                  </option>
                ))}
              </select>
            </label>
            {choice === 'monthly-bill' && billPlan?.bill && (
              <p>
                {billPlan.bill.name} · {fmt(billPlan.bill.amount)}/month from{' '}
                {monthLabel(billPlan.bill.start_month)}
              </p>
            )}
            <p className="muted">
              Savings comes from Recurring accounts. Purchase planner owns
              payment and purchase estimates; the advisor explains their
              calculated results.
            </p>
            <button className="secondary" onClick={onOpenPlanner}>
              Open Purchase planner
            </button>
            {context?.purchase_scenario && (
              <div
                className={
                  'scenario-result ' +
                  (context.purchase_scenario.would_exceed_forecast
                    ? 'over'
                    : '')
                }
              >
                <small>
                  {context.purchase_scenario.name} ·{' '}
                  {monthLabel(context.purchase_scenario.month, true)}
                </small>
                <span>Remaining after purchase</span>
                <strong>
                  {fmt(
                    context.purchase_scenario.remaining_after_purchase_minor,
                  )}
                </strong>
                <small>
                  {context.purchase_scenario.already_included
                    ? 'Already included in the baseline.'
                    : 'Draft estimate; excluded from your saved forecast.'}
                </small>
              </div>
            )}
          </div>
        </section>
        {context?.forecast_comparison && (
          <section className="panel">
            <div className="section-head">
              <div>
                <h2>What changed this month?</h2>
                <p>
                  {monthLabel(context.forecast_comparison.previous_month)} →{' '}
                  {monthLabel(context.forecast_comparison.month)} · forecast
                  only
                </p>
              </div>
            </div>
            <div className="advisor-context">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Forecast</th>
                      <th>Previous</th>
                      <th>Selected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ['income_minor', 'Income'],
                        ['expenses_minor', 'Expenses'],
                        ['remaining_minor', 'Remaining'],
                      ] as const
                    ).map(([key, label]) => (
                      <tr key={key}>
                        <th>{label}</th>
                        <td>
                          {fmt(context.forecast_comparison.previous[key])}
                        </td>
                        <td>{fmt(context.forecast_comparison.current[key])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!context.forecast_comparison.previous.income_recorded && (
                <p className="red">
                  Previous-month income is unrecorded; the comparison may be
                  incomplete.
                </p>
              )}
              {context.forecast_comparison.changes.length ? (
                <div className="forecast-change-list">
                  {context.forecast_comparison.changes.map((line, i) => (
                    <div key={i}>
                      <strong>{line.name}</strong>
                      <small>
                        {line.kind === 'receivable'
                          ? 'Income'
                          : (line.category ?? 'Expense')}{' '}
                        ·{' '}
                        {line.source === 'included_purchase'
                          ? 'included purchase'
                          : line.frequency === 'annual'
                            ? line.annual_distributed
                              ? 'annual allocation'
                              : 'annual payment'
                            : line.change.replaceAll('_', ' ')}
                      </small>
                      <p>
                        {fmt(line.previous_minor)} → {fmt(line.current_minor)}{' '}
                        <small>
                          Effect on remaining budget:{' '}
                          {line.remaining_impact_minor > 0 ? '+' : ''}
                          {fmt(line.remaining_impact_minor)}
                        </small>
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p>No forecast amounts changed from the previous month.</p>
              )}
              <p>
                Actual spending and category guides are separate. Suggested
                changes stay hypothetical until you update your budget.
              </p>
              <button className="text-button" onClick={onOpenPlanner}>
                Preview changes in Purchase planner →
              </button>
            </div>
          </section>
        )}
        {context?.savings_projection && (
          <section className="panel">
            <div className="section-head">
              <div>
                <h2>Calculated budget impact</h2>
                <p>
                  {context.savings_projection.horizon_months} full months ·
                  starting {monthLabel(context.savings_projection.start_month)}
                </p>
              </div>
            </div>
            <div className="advisor-context">
              {context.savings_projection.savings_known ? (
                <>
                  <p>
                    Starting savings:{' '}
                    {fmt(context.savings_projection.starting_savings)}. Savings
                    floor: {fmt(context.savings_projection.savings_floor)}.
                  </p>
                  <p>
                    Projected ending savings:{' '}
                    <strong>
                      {fmt(context.savings_projection.ending_savings)}
                    </strong>
                    . Lowest savings:{' '}
                    <strong>
                      {fmt(context.savings_projection.lowest_savings)}
                    </strong>
                    .
                  </p>
                </>
              ) : (
                <p>
                  Savings is not set; this compares monthly budget room only.
                </p>
              )}
              {context.savings_projection.first_bill_month_remaining !==
                null && (
                <p>
                  Monthly room after the payment:{' '}
                  <strong>
                    {fmt(context.savings_projection.first_bill_month_remaining)}
                  </strong>{' '}
                  in the first active month.
                </p>
              )}
              {context.savings_projection.bill && (
                <p>
                  {context.savings_projection.bill.name}:{' '}
                  {fmt(context.savings_projection.bill.amount)}/month from{' '}
                  {monthLabel(context.savings_projection.bill.start_month)}.
                  {context.savings_projection.bill.already_included
                    ? ' Already included; not deducted twice.'
                    : ''}
                </p>
              )}
              {context.savings_projection.bill_inferred_from_question && (
                <p>
                  Assumes the new bill starts in the selected budget month. Use
                  Purchase planner for a different start or end.
                </p>
              )}
              {context.savings_projection.first_below_floor_month && (
                <p className="red">
                  Below savings floor in{' '}
                  {monthLabel(
                    context.savings_projection.first_below_floor_month,
                  )}
                  .
                </p>
              )}
              {context.savings_projection.first_negative_month && (
                <p className="red">
                  Below zero in{' '}
                  {monthLabel(context.savings_projection.first_negative_month)}.
                </p>
              )}
              {!context.savings_projection.income_complete && (
                <p className="red">
                  Income is missing in part of the forecast; affordability is
                  incomplete.
                </p>
              )}
              <p>
                Dated annual bills replace monthly allocations with their full
                payment when due. This is a planning projection, not a live bank
                balance.
              </p>
            </div>
          </section>
        )}
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Budget context</h2>
              <p>Freshly read with every question.</p>
            </div>
          </div>
          <div className="advisor-context">
            <p>
              {monthLabel(month)} and the following {useWeb ? 23 : 11} months of
              forecasts; three months of category spending; upcoming draft
              purchases; and your selected scenario.
            </p>
            <p>
              No bank balances, raw statements, card identifiers, or individual
              transaction descriptions are sent to the model. Travel search
              terms are sent to Brave when enabled. Chat stays in this tab’s
              memory.
            </p>
            {context && (
              <details>
                <summary>View the snapshot used for the last answer</summary>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th>Income</th>
                        <th>Expenses</th>
                        <th>Remaining</th>
                      </tr>
                    </thead>
                    <tbody>
                      {context.monthly_forecasts.map((f) => (
                        <tr key={f.month}>
                          <th>{monthLabel(f.month, true)}</th>
                          <td>{fmt(f.income_minor)}</td>
                          <td>{fmt(f.expenses_minor)}</td>
                          <td className={f.remaining_minor < 0 ? 'red' : ''}>
                            {fmt(f.remaining_minor)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="snapshot-actuals">
                  <h3>Hypothetical trip funding</h3>
                  <p>{context.planning_capacity.basis}</p>
                  <p>
                    Starting trip funds:{' '}
                    {context.planning_capacity.available_savings_minor === null
                      ? 'unknown'
                      : fmt(context.planning_capacity.available_savings_minor)}
                    . Monthly buffer:{' '}
                    {context.planning_capacity.monthly_buffer_minor === null
                      ? 'unknown'
                      : fmt(context.planning_capacity.monthly_buffer_minor)}
                    .
                  </p>
                  {context.planning_capacity
                    .earliest_funded_month_for_selected_scenario && (
                    <p>
                      Selected estimate could be funded by{' '}
                      {monthLabel(
                        context.planning_capacity
                          .earliest_funded_month_for_selected_scenario,
                      )}{' '}
                      under these assumptions; this is not a cash-balance
                      guarantee.
                    </p>
                  )}
                  {context.planning_capacity.buffer_shortfall_months.length >
                    0 && (
                    <p className="red">
                      Buffer shortfalls:{' '}
                      {context.planning_capacity.buffer_shortfall_months.join(
                        ', ',
                      )}
                      .
                    </p>
                  )}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Month</th>
                          <th>Potential contribution</th>
                          <th>Hypothetical trip fund</th>
                        </tr>
                      </thead>
                      <tbody>
                        {context.planning_capacity.months.map((p) => (
                          <tr key={p.month}>
                            <th>{monthLabel(p.month, true)}</th>
                            <td>
                              {p.potential_contribution_minor === null
                                ? 'Unknown'
                                : fmt(p.potential_contribution_minor)}
                            </td>
                            <td>
                              {p.hypothetical_trip_fund_minor === null
                                ? 'Unknown'
                                : fmt(p.hypothetical_trip_fund_minor)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {context.recent_actuals.map((a) => (
                    <div key={a.month}>
                      <strong>
                        {monthLabel(a.month, true)} · {a.status}
                      </strong>
                      <p>
                        {a.total_spending_minor === null
                          ? 'Missing actuals'
                          : fmt(a.total_spending_minor) + ' recorded spending'}
                      </p>
                      {a.categories.map((c) => (
                        <small key={c.name}>
                          {c.name}: {fmt(c.spending_minor)}
                        </small>
                      ))}
                    </div>
                  ))}
                  <h3>Draft estimates excluded from forecast</h3>
                  {context.draft_purchases.length ? (
                    context.draft_purchases.map((p, i) => (
                      <p key={i}>
                        {p.name} · {p.month} · {fmt(p.amount_minor)}
                      </p>
                    ))
                  ) : (
                    <p>No upcoming drafts.</p>
                  )}
                  {context.additional_drafts_omitted > 0 && (
                    <p>
                      {context.additional_drafts_omitted} additional drafts
                      omitted.
                    </p>
                  )}
                  <p>
                    Each month stands on its own. Savings and bank balances are
                    unknown.
                  </p>
                </div>
              </details>
            )}
          </div>
        </section>
      </aside>
    </div>
  );
}
