import { useEffect, useRef, useState } from 'react';
import {
  ChevronRight,
  LoaderCircle,
  Pencil,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { api } from './api';
import type { Category } from './api';

type Rule = {
  id: string;
  payee: string;
  kind: string;
  category_id: string;
  category: string;
  group_id: string | null;
  group_name: string | null;
};
type Group = { id: string; name: string; kind: string; members: Rule[] };
type Suggestion = {
  id: string;
  name: string;
  kind: string;
  reason: string;
  members: Rule[];
  member_ids: string[];
  category_conflict: boolean;
  suggested_category_id: string | null;
};
type Review = {
  id: string;
  status: string;
  progress: number;
  total: number;
  error: string;
  suggestions: Suggestion[];
  result: null | { updated_rule_count: number; group_ids: string[] };
};
type Summary = {
  total: number;
  groups: Group[];
  ungrouped: Rule[];
  review: Review | null;
};
type Choice = {
  checked: boolean;
  name: string;
  members: string[];
  category: string;
};
const running = (review: Review | null) =>
  !!review && ['queued', 'running'].includes(review.status);

export default function RememberedPayees({
  categories,
  model,
  revision,
  onChanged,
}: {
  categories: Category[];
  model: string;
  revision: number;
  onChanged: () => void;
}) {
  const [data, setData] = useState<Summary | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [groupName, setGroupName] = useState('');
  const [reload, setReload] = useState(0);
  const initialized = useRef<string | null>(null);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    api<Summary>('/payee-review/payees', 'GET', undefined, controller.signal)
      .then((value) => {
        if (active) {
          setData(value);
          setReview(value.review);
        }
      })
      .catch((e) => {
        if (active && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [revision, reload]);
  const activeReviewId = running(review) ? review!.id : null;
  useEffect(() => {
    if (!activeReviewId) return;
    let active = true;
    const controller = new AbortController();
    const timer = setInterval(() => {
      api<Review>(
        '/payee-review/reviews/' + activeReviewId,
        'GET',
        undefined,
        controller.signal,
      )
        .then((value) => {
          if (active) setReview(value);
        })
        .catch((e) => {
          if (active && e.name !== 'AbortError') setError(e.message);
        });
    }, 1500);
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [activeReviewId]);
  useEffect(() => {
    if (review?.status === 'ready' && initialized.current !== review.id) {
      initialized.current = review.id;
      setChoices(
        Object.fromEntries(
          review.suggestions.map((group) => [
            group.id,
            {
              checked: false,
              name: group.name,
              members: group.member_ids,
              category: '',
            },
          ]),
        ),
      );
    }
  }, [review]);
  const update = (id: string, patch: Partial<Choice>) =>
    setChoices((previous) => ({
      ...previous,
      [id]: { ...previous[id], ...patch },
    }));
  const perform = async (action: () => Promise<unknown>, refresh = true) => {
    setBusy(true);
    setError('');
    try {
      await action();
      if (refresh) {
        setReload((value) => value + 1);
        onChanged();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const start = () =>
    void perform(async () => {
      setReview(await api<Review>('/payee-review/reviews', 'POST'));
    }, false);
  const selected = Object.entries(choices).filter(
    ([, choice]) => choice.checked,
  );
  const valid =
    selected.length > 0 &&
    selected.length <= 200 &&
    selected.every(
      ([, choice]) => choice.name.trim() && choice.members.length >= 2,
    );
  const memberRow = (rule: Rule) => (
    <div className="payee-member" key={rule.id}>
      <div className="grow">
        <strong>{rule.payee}</strong>
        <small>{rule.kind}</small>
      </div>
      <label>
        <span className="sr-only">Category for {rule.payee}</span>
        <select
          aria-label={`Category for ${rule.payee}`}
          value={rule.category_id}
          disabled={busy}
          onChange={(event) =>
            void perform(() =>
              api('/payee-rules/' + rule.id, 'PUT', {
                category_id: event.target.value,
              }),
            )
          }
        >
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
      <button
        className="icon"
        disabled={busy}
        aria-label={`Forget ${rule.payee}`}
        onClick={() => {
          if (
            window.confirm(
              `Forget the remembered alias ${rule.payee}? Saved transactions remain unchanged.`,
            )
          )
            void perform(() => api('/payee-rules/' + rule.id, 'DELETE'));
        }}
      >
        <Trash2 size={15} />
      </button>
    </div>
  );
  return (
    <details className="panel remembered-payees">
      <summary className="section-head">
        <div>
          <h2>
            Remembered payees{' '}
            <span className="settings-count">{data?.total ?? '…'}</span>
          </h2>
          <p>
            Approved merchant groups, exact aliases, and your saved category
            corrections.
          </p>
        </div>
        <ChevronRight size={18} aria-hidden="true" />
      </summary>
      <div className="payee-review-content">
        <p className="muted">
          Review likely name variations with your installed local model.
          Applying a review updates future matching; saved expenses and original
          descriptions stay unchanged.
        </p>
        <div className="button-group">
          <button
            className="secondary"
            disabled={
              busy || running(review) || !model || !data || data.total < 2
            }
            onClick={start}
          >
            <Sparkles size={15} />
            Review similar payees
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => setReload((value) => value + 1)}
          >
            Refresh payees
          </button>
        </div>
        {!model && (
          <p className="notice">
            Choose an installed local model in Settings to review similar
            payees.
          </p>
        )}
        {error && (
          <p className="notice danger" role="alert">
            {error}
          </p>
        )}
        {running(review) && (
          <div className="notice payee-review-progress" role="status">
            <LoaderCircle className="spin" size={16} />
            <span>
              Reviewing locally · {review!.progress} of {review!.total || '…'}{' '}
              batches. No payees have been changed.
            </span>
            <button
              className="text-button"
              disabled={busy}
              onClick={() =>
                void perform(
                  async () =>
                    setReview(
                      await api<Review>(
                        '/payee-review/reviews/' + review!.id,
                        'DELETE',
                      ),
                    ),
                  false,
                )
              }
            >
              Cancel review
            </button>
          </div>
        )}
        {review && ['failed', 'interrupted'].includes(review.status) && (
          <p className="notice danger" role="alert">
            {review.error}
          </p>
        )}
        {review?.status === 'cancelled' && (
          <p role="status">
            Review discarded. Remembered payees were not changed.
          </p>
        )}
        {review?.status === 'applied' && (
          <p className="notice" role="status">
            Applied approved groups to {review.result?.updated_rule_count}{' '}
            remembered aliases. Exact category edits continue to take priority.
          </p>
        )}
        {review?.status === 'ready' && (
          <section
            className="payee-review-results"
            aria-label="Suggested payee updates"
          >
            <div className="payee-review-heading">
              <h3>{review.suggestions.length} proposed groups</h3>
              {review.suggestions.length > 0 && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    setChoices((previous) =>
                      Object.fromEntries(
                        Object.entries(previous).map(([id, choice], index) => [
                          id,
                          { ...choice, checked: index < 200 },
                        ]),
                      ),
                    )
                  }
                >
                  Select all suggestions
                </button>
              )}
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  void perform(
                    async () =>
                      setReview(
                        await api<Review>(
                          '/payee-review/reviews/' + review.id,
                          'DELETE',
                        ),
                      ),
                    false,
                  )
                }
              >
                Discard review
              </button>
            </div>
            {!review.suggestions.length ? (
              <p>
                No likely groups were suggested. Existing aliases remain as
                saved.
              </p>
            ) : (
              <>
                <p className="muted">
                  Select groups to approve. Keep individual categories unless
                  you explicitly choose a shared category. A merchant can belong
                  to multiple spending categories.
                </p>
                {review.suggestions.map((group) => {
                  const choice = choices[group.id];
                  if (!choice) return null;
                  return (
                    <fieldset
                      className="payee-suggestion"
                      key={group.id}
                      disabled={busy}
                    >
                      <legend>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={choice.checked}
                            onChange={(event) =>
                              update(group.id, {
                                checked: event.target.checked,
                              })
                            }
                          />
                          Approve {group.name}
                        </label>
                      </legend>
                      <p>
                        {group.reason} · {group.kind}
                      </p>
                      {group.category_conflict && (
                        <p className="notice">
                          Different categories are present. They will be
                          preserved unless you choose a category below.
                        </p>
                      )}
                      <div className="form-grid">
                        <label>
                          Group name
                          <input
                            aria-label={`Group name for ${group.name}`}
                            maxLength={160}
                            value={choice.name}
                            onChange={(event) =>
                              update(group.id, { name: event.target.value })
                            }
                          />
                        </label>
                        <label>
                          Category change
                          <select
                            aria-label={`Category change for ${group.name}`}
                            value={choice.category}
                            onChange={(event) =>
                              update(group.id, { category: event.target.value })
                            }
                          >
                            <option value="">Keep individual categories</option>
                            {categories.map((category) => (
                              <option key={category.id} value={category.id}>
                                Set selected aliases to {category.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <ul className="payee-proposed-members">
                        {group.members.map((member) => (
                          <li key={member.id}>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                aria-label={`Include ${member.payee} in ${group.name}`}
                                checked={choice.members.includes(member.id)}
                                onChange={(event) =>
                                  update(group.id, {
                                    members: event.target.checked
                                      ? [...choice.members, member.id]
                                      : choice.members.filter(
                                          (id) => id !== member.id,
                                        ),
                                  })
                                }
                              />
                              <span>
                                {member.payee}
                                <small>
                                  {member.category}
                                  {member.group_name
                                    ? ' · existing group: ' + member.group_name
                                    : ''}
                                </small>
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                      {choice.members.length < 2 && (
                        <p className="red">
                          Select at least two aliases for this group, or leave
                          the group unapproved.
                        </p>
                      )}
                    </fieldset>
                  );
                })}
                <button
                  disabled={busy || !valid}
                  onClick={() =>
                    void perform(async () => {
                      setReview(
                        await api<Review>(
                          '/payee-review/reviews/' + review.id + '/apply',
                          'POST',
                          {
                            groups: selected.map(([id, choice]) => ({
                              suggestion_id: id,
                              name: choice.name,
                              member_ids: choice.members,
                              category_id: choice.category || null,
                            })),
                          },
                        ),
                      );
                    })
                  }
                >
                  Apply selected changes ({selected.length})
                </button>
              </>
            )}
          </section>
        )}
        {data?.groups.length ? (
          <>
            <h3 className="payee-list-title">Approved groups</h3>
            {data.groups.map((group) => (
              <details className="payee-approved-group" key={group.id}>
                <summary>
                  <strong>{group.name}</strong>
                  <span>
                    {group.kind} · {group.members.length} aliases
                  </span>
                </summary>
                <div className="button-group">
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => {
                      setEditing(group.id);
                      setGroupName(group.name);
                    }}
                  >
                    <Pencil size={14} />
                    Rename group
                  </button>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Ungroup ${group.name}? All remembered aliases and their individual categories will be kept.`,
                        )
                      )
                        void perform(() =>
                          api('/payee-review/groups/' + group.id, 'DELETE'),
                        );
                    }}
                  >
                    Ungroup
                  </button>
                </div>
                {editing === group.id && (
                  <form
                    className="payee-rename-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void perform(async () => {
                        await api('/payee-review/groups/' + group.id, 'PUT', {
                          name: groupName,
                        });
                        setEditing(null);
                      });
                    }}
                  >
                    <input
                      aria-label="New payee group name"
                      maxLength={160}
                      required
                      value={groupName}
                      disabled={busy}
                      onChange={(event) => setGroupName(event.target.value)}
                    />
                    <button disabled={busy}>Save name</button>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setEditing(null)}
                    >
                      Cancel
                    </button>
                  </form>
                )}
                {group.members.map(memberRow)}
              </details>
            ))}
          </>
        ) : null}
        {!!data?.ungrouped.length && (
          <>
            <h3 className="payee-list-title">
              Individual payees ({data.ungrouped.length})
            </h3>
            {data.ungrouped.map(memberRow)}
          </>
        )}
        {data?.total === 0 && (
          <p>
            Save a categorized transaction or commit a reviewed import to
            remember its payee. Then review similar variants here.
          </p>
        )}
      </div>
    </details>
  );
}
