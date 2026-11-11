import { useEffect, useRef, useState } from 'react';
import {
  MessageCircle,
  Send,
  RotateCcw,
  LoaderCircle,
  Globe,
  X,
  Plus,
} from 'lucide-react';
import { api, money } from './api';
import AdvisorMarkdown from './AdvisorMarkdown';
import AdvisorComparison from './AdvisorComparison';
import type { SpendingComparison } from './AdvisorComparison';
import AdvisorHistory from './AdvisorHistory';
import { RememberExchange } from './AdvisorMemory';
import type { MemoryRecall } from './AdvisorMemory';
import type { AdvisorSpendingHistory } from './api';
import type { PlanDraft, PlanItem } from './Planning';

type Research = {
  status: string;
  queries: string[];
  warnings: string[];
  missing_details: string[];
  sources: {
    id: string;
    title: string;
    url: string;
    snippet: string;
    retrieved_at: string;
  }[];
};
type Context = {
  advisor_memory?: MemoryRecall;
  web_research?: Research;
  spending_comparison?: SpendingComparison | null;
  spending_history?: AdvisorSpendingHistory;
  monthly_forecasts?: {
    month: string;
    income_minor: number;
    expenses_minor: number;
    remaining_minor: number;
  }[];
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  failed?: boolean;
  truncated?: boolean;
  research?: Research;
  memory?: MemoryRecall;
};
type Preview = {
  topic: string;
  queries: string[];
  missing_details: string[];
  confirmation: string;
};

export default function BudgetAdvisor({
  entry,
  month,
  currency,
  model,
  memoryEnabled = false,
  revision,
  planId = null,
  onClearPlan,
  onCreatePlan,
}: {
  entry: { question: string; key: number } | null;
  month: string;
  currency: string;
  model: string;
  memoryEnabled?: boolean;
  revision: number;
  planId?: string | null;
  onClearPlan?: () => void;
  onCreatePlan?: (draft: PlanDraft) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [context, setContext] = useState<Context | null>(null);
  const [contextRevision, setContextRevision] = useState(revision);
  const [plan, setPlan] = useState<PlanItem | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState('');
  const [useWeb, setUseWeb] = useState(false);
  const [webStatus, setWebStatus] = useState({ available: false, message: '' });
  const [topic, setTopic] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [approved, setApproved] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [drafting, setDrafting] = useState<number | null>(null);
  const pending = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const memoryEpoch = useRef<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const clearPlan = useRef(onClearPlan);
  clearPlan.current = onClearPlan;
  const reset = () => {
    pending.current++;
    controller.current?.abort();
    setMessages([]);
    setContext(null);
    setError('');
    setBusy(false);
    memoryEpoch.current = null;
  };
  const refreshWeb = async () => {
    try {
      setWebStatus(await api('/advisor/research-status'));
    } catch (e) {
      setWebStatus({ available: false, message: (e as Error).message });
    }
  };
  useEffect(() => {
    void refreshWeb();
  }, []);
  useEffect(() => {
    reset();
    setQuestion('');
  }, [month, currency, model, memoryEnabled]);
  useEffect(() => {
    const changed = () => {
      reset();
      setQuestion('');
    };
    window.addEventListener('abacus-memory-changed', changed);
    const channel =
      typeof BroadcastChannel !== 'undefined'
        ? new BroadcastChannel('abacus-memory')
        : null;
    if (channel) channel.onmessage = changed;
    return () => {
      window.removeEventListener('abacus-memory-changed', changed);
      channel?.close();
    };
  }, []);
  useEffect(() => {
    let active = true;
    if (!planId) {
      setPlan(null);
      return;
    }
    const read = () =>
      api<PlanItem>('/planning/' + planId)
        .then((item) => {
          if (active) {
            setPlan(item);
            setNotice('');
          }
        })
        .catch((error: Error & { status?: number }) => {
          if (active) {
            if (error.status !== 404) {
              setNotice(
                'Could not refresh this plan. Try again before relying on its funding details.',
              );
              return;
            }
            pending.current++;
            controller.current?.abort();
            setBusy(false);
            setPlan(null);
            setNotice(
              'This plan is no longer available. Choose a current item from Planning.',
            );
            clearPlan.current?.();
          }
        });
    setPlan(null);
    void read();
    window.addEventListener('focus', read);
    return () => {
      active = false;
      window.removeEventListener('focus', read);
    };
  }, [planId, revision]);
  useEffect(() => {
    pending.current++;
    controller.current?.abort();
    setBusy(false);
  }, [planId]);
  useEffect(() => {
    if (entry) {
      setQuestion(entry.question);
      setUseWeb(false);
      setPreview(null);
      setApproved(false);
    }
  }, [entry]);
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
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' });
  }, [messages, busy, error]);
  useEffect(
    () => () => {
      pending.current++;
      controller.current?.abort();
    },
    [],
  );
  const previewSearch = async () => {
    setPreviewing(true);
    setError('');
    setApproved(false);
    try {
      setPreview(
        await api('/advisor/research-preview', 'POST', { topic: topic.trim() }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPreviewing(false);
    }
  };
  const send = async () => {
    const text = question.trim();
    if (!text || busy) return;
    if (planId && !plan) {
      setError('Wait for the current Planning item to load, or clear it.');
      return;
    }
    if (
      useWeb &&
      (!approved || !preview?.queries.length || preview.topic !== topic.trim())
    ) {
      setError(
        'Preview and confirm the public search terms before asking with web search.',
      );
      return;
    }
    const history = messages.filter((item) => !item.failed);
    const id = ++pending.current;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError('');
    setMessages([...history, { role: 'user', content: text }]);
    setQuestion('');
    try {
      const result = await api<{
        reply: string;
        reply_truncated?: boolean;
        context: Context;
      }>(
        '/advisor/chat',
        'POST',
        {
          month,
          message: text,
          history: history.slice(-12).map((item) => ({
            role: item.role,
            content: item.content.slice(0, 2000),
          })),
          memory_epoch: memoryEpoch.current,
          plan_id: planId,
          use_web: useWeb,
          research_topic: useWeb ? topic.trim() : '',
          research_confirmation: useWeb ? preview?.confirmation : undefined,
        },
        request.signal,
      );
      if (id !== pending.current) return;
      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: result.reply,
          truncated: result.reply_truncated,
          research: result.context.web_research,
          memory: result.context.advisor_memory,
        },
      ]);
      setContext(result.context);
      setContextRevision(revision);
      memoryEpoch.current = result.context.advisor_memory?.epoch ?? null;
    } catch (e) {
      if (id !== pending.current) return;
      setMessages([...history, { role: 'user', content: text, failed: true }]);
      setQuestion(text);
      if ((e as Error).name !== 'AbortError') setError((e as Error).message);
      if (
        planId &&
        [404, 409].includes((e as Error & { status: number }).status)
      ) {
        try {
          setPlan(await api<PlanItem>('/planning/' + planId));
        } catch (refreshError) {
          if ((refreshError as Error & { status: number }).status === 404) {
            setPlan(null);
            clearPlan.current?.();
          }
        }
      }
    } finally {
      if (id === pending.current) setBusy(false);
    }
  };
  const draft = async (index: number) => {
    setDrafting(index);
    setError('');
    try {
      const value = await api<PlanDraft>('/planning/draft', 'POST', {
        user_message: messages[index - 1]?.content ?? '',
        assistant_message: messages[index].content,
      });
      onCreatePlan?.(value);
    } catch {
      onCreatePlan?.({});
    } finally {
      setDrafting(null);
    }
  };
  return (
    <div className="advisor-layout advisor-simple">
      <div className="advisor-main">
        <section className="panel advisor-chat">
          <div className="section-head">
            <div>
              <h2>
                <MessageCircle size={18} />
                Budget advisor
              </h2>
              <p>Understand your spending. Research an idea. Make a plan.</p>
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
          {plan && (
            <div className="advisor-plan-chip">
              <span>
                Discussing: <strong>{plan.name}</strong> ·{' '}
                {money(plan.amount, currency)} · {plan.target_date}
              </span>
              <button
                className="icon"
                aria-label="Clear discussed plan"
                onClick={() => clearPlan.current?.()}
              >
                <X size={14} />
              </button>
            </div>
          )}
          {notice && (
            <p className="notice" role="status">
              {notice}
            </p>
          )}
          {context && contextRevision !== revision && (
            <p className="notice" role="status">
              Budget entries changed since this answer. Your conversation is
              kept; ask a follow-up to use a fresh budget snapshot.
            </p>
          )}
          <div
            className="chat-messages"
            role="log"
            aria-live="polite"
            aria-label="Budget conversation"
          >
            {!messages.length && !busy && (
              <div className="advisor-welcome">
                <h3>A little perspective before you decide.</h3>
                <p>
                  Use your saved budget and Planning goals, or explore something
                  new.
                </p>
                <div className="suggestions">
                  {[
                    'What could I do to increase my savings?',
                    'Can I fund my plans by their target dates?',
                    'Help me plan a vacation.',
                    'Help me compare a planned purchase.',
                  ].map((text) => (
                    <button
                      key={text}
                      className="secondary"
                      onClick={() => setQuestion(text)}
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((item, index) => (
              <article className={'chat-message ' + item.role} key={index}>
                <span>{item.role === 'user' ? 'You' : 'Budget advisor'}</span>
                {item.role === 'assistant' ? (
                  <AdvisorMarkdown
                    content={item.content}
                    sources={item.research?.sources}
                  />
                ) : (
                  <p>{item.content}</p>
                )}
                {item.failed && (
                  <p className="muted">
                    This question could not be completed. It is kept below so
                    you can retry.
                  </p>
                )}
                {item.truncated && (
                  <p className="notice" role="status">
                    This answer reached the local model’s reply limit and is
                    incomplete. Ask a shorter follow-up for the remaining
                    details.
                  </p>
                )}
                {item.memory?.warnings.map((warning) => (
                  <p className="notice" role="status" key={warning}>
                    {warning}
                  </p>
                ))}
                {!!item.memory?.notes.length && (
                  <details>
                    <summary>Memory used for this answer</summary>
                    {item.memory.notes.map((note, i) => (
                      <div className="memory-note" key={note.id}>
                        <strong>
                          [M{i + 1}] {note.title}
                        </strong>
                        <small>{note.source_date}</small>
                        <p>{note.text}</p>
                      </div>
                    ))}
                  </details>
                )}
                {item.research && item.research.status !== 'disabled' && (
                  <div className="research-results">
                    <small>Web research · {item.research.status}</small>
                    {item.research.warnings?.map((warning) => (
                      <p key={warning}>{warning}</p>
                    ))}
                    {item.research.missing_details?.map((detail) => (
                      <p key={detail}>{detail}</p>
                    ))}
                    {item.research.sources?.map((source) => (
                      <a
                        key={source.id}
                        className="source-link"
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        [{source.id}] {source.title}
                        <small>{source.retrieved_at}</small>
                      </a>
                    ))}
                  </div>
                )}
                {item.role === 'assistant' && (
                  <div className="advisor-message-actions">
                    {onCreatePlan && (
                      <button
                        className="text-button"
                        disabled={drafting !== null}
                        onClick={() => void draft(index)}
                      >
                        <Plus size={14} />
                        {drafting === index
                          ? 'Preparing plan…'
                          : 'Add to Planning'}
                      </button>
                    )}
                    {memoryEnabled && messages[index - 1]?.role === 'user' && (
                      <RememberExchange
                        user={messages[index - 1].content}
                        assistant={item.content}
                      />
                    )}
                  </div>
                )}
              </article>
            ))}
            {busy && (
              <div className="chat-thinking">
                <LoaderCircle className="spin" size={17} />
                Thinking… {elapsed}s
                <button
                  className="text-button"
                  onClick={() => {
                    pending.current++;
                    controller.current?.abort();
                    setBusy(false);
                  }}
                >
                  Cancel
                </button>
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
            {error && (
              <p className="notice danger" role="alert">
                {error}
              </p>
            )}
            <label htmlFor="advisor-question" className="sr-only">
              Ask about your budget
            </label>
            <textarea
              id="advisor-question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={
                plan
                  ? `Ask about ${plan.name}…`
                  : 'Ask about your budget, a trip, or a purchase…'
              }
              disabled={busy}
              maxLength={2000}
            />
            <div className="chat-compose-actions">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={useWeb}
                  disabled={busy || !webStatus.available}
                  onChange={(e) => {
                    setUseWeb(e.target.checked);
                    setApproved(false);
                  }}
                />
                <Globe size={14} />
                Enable web search
              </label>
              <button
                disabled={busy || !question.trim() || (!!planId && !plan)}
              >
                <Send size={15} />
                Ask
              </button>
            </div>
            {!webStatus.available && (
              <small>
                {webStatus.message || 'Checking web search connection…'}{' '}
                <button
                  type="button"
                  className="text-button"
                  onClick={() => void refreshWeb()}
                >
                  Refresh connection
                </button>
              </small>
            )}
            {useWeb && (
              <div className="chat-web-controls">
                <label>
                  Public search topic
                  <input
                    aria-label="Public search topic"
                    value={topic}
                    maxLength={1000}
                    disabled={busy}
                    placeholder="Destination and dates, or a product and region"
                    onChange={(e) => {
                      setTopic(e.target.value);
                      setPreview(null);
                      setApproved(false);
                    }}
                  />
                </label>
                <small>
                  Only the public topic and approved searches leave Abacus. Keep
                  personal finances in the chat.
                </small>
                <button
                  type="button"
                  className="secondary small"
                  disabled={busy || previewing || !topic.trim()}
                  onClick={() => void previewSearch()}
                >
                  {previewing ? 'Preparing…' : 'Preview public searches'}
                </button>
                {preview && (
                  <>
                    <ul>
                      {preview.queries.map((query) => (
                        <li key={query}>{query}</li>
                      ))}
                    </ul>
                    {preview.missing_details.map((detail) => (
                      <p key={detail}>{detail}</p>
                    ))}
                    {!!preview.queries.length && (
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={approved}
                          onChange={(e) => setApproved(e.target.checked)}
                          disabled={busy}
                        />
                        I approve sending these search terms to Brave.
                      </label>
                    )}
                  </>
                )}
              </div>
            )}
            <small>
              Read-only guidance from your local model. Add to Planning opens a
              draft for review.
            </small>
          </form>
        </section>
        {context?.spending_comparison && (
          <AdvisorComparison
            comparison={context.spending_comparison}
            currency={currency}
          />
        )}
        {context?.spending_history && (
          <section className="panel advisor-evidence">
            <div className="section-head">
              <div>
                <h2>Spending evidence</h2>
                <p>Recorded categories and payees behind the advice.</p>
              </div>
            </div>
            <AdvisorHistory
              history={context.spending_history}
              currency={currency}
            />
          </section>
        )}
        {context?.monthly_forecasts && (
          <details className="panel advisor-snapshot">
            <summary>Budget snapshot used for the last answer</summary>
            <p>
              Financial context and approved memories stay local. Forecasts are
              estimates; recorded savings is manually entered.
            </p>
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
                  {context.monthly_forecasts.map((row) => (
                    <tr key={row.month}>
                      <th>{row.month}</th>
                      <td>{money(row.income_minor, currency)}</td>
                      <td>{money(row.expenses_minor, currency)}</td>
                      <td>{money(row.remaining_minor, currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
