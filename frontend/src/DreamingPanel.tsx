import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { memoryChanged } from './AdvisorMemory';
import type { MemoryNote } from './AdvisorMemory';

type Group = {
  operation_key: string;
  state: string;
  note?: MemoryNote;
  evidence?: MemoryNote[];
  reasons?: string[];
  preserved_facts?: string[];
  result_id?: string;
};
type State = {
  enabled: boolean;
  epoch: string;
  pending_review: number;
  jobs: { id: string; state: string; reason: string; groups: Group[] }[];
};

function Review({
  group,
  apply,
}: {
  group: Group;
  apply: (note: MemoryNote) => Promise<void>;
}) {
  const [note, setNote] = useState(group.note!);
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        try {
          await apply(note);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        Combined title
        <input
          required
          maxLength={100}
          value={note.title}
          onChange={(e) => setNote({ ...note, title: e.target.value })}
        />
      </label>
      <label>
        Combined memory
        <textarea
          required
          maxLength={400}
          value={note.text}
          onChange={(e) => setNote({ ...note, text: e.target.value })}
        />
      </label>
      {group.reasons?.map((reason) => (
        <p key={reason}>{reason}</p>
      ))}
      {!!group.preserved_facts?.length && (
        <details>
          <summary>Proposed preserved facts</summary>
          {group.preserved_facts.map((fact, i) => (
            <p key={i}>{fact}</p>
          ))}
        </details>
      )}
      <details>
        <summary>Original memories and evidence</summary>
        {group.evidence?.map((source) => (
          <article key={source.id}>
            <strong>
              {source.title} · {source.source_date}
            </strong>
            <p>{source.text}</p>
            <blockquote>{source.source_excerpt}</blockquote>
          </article>
        ))}
      </details>
      <button disabled={busy}>
        {busy ? 'Saving…' : 'Approve consolidation'}
      </button>
    </form>
  );
}

export default function DreamingPanel() {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const value = await api<State>('/advisor/dreaming');
      setState((previous) => {
        if (previous && previous.epoch !== value.epoch)
          queueMicrotask(memoryChanged);
        return value;
      });
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => clearInterval(timer);
  }, [load]);
  const act = async (path: string, method = 'POST', data?: unknown) => {
    setBusy(true);
    setError('');
    try {
      await api(path, method, data);
      memoryChanged();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="dreaming-settings">
      <h3>Memory dreaming</h3>
      <p>
        Combine related memories while the advisor is idle. Originals are
        retained; uncertain changes need review.
      </p>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={state?.enabled ?? false}
          disabled={!state || busy}
          onChange={(e) =>
            void act('/advisor/dreaming', 'PUT', { enabled: e.target.checked })
          }
        />
        Enable dreaming
      </label>
      <button
        className="secondary"
        disabled={!state?.enabled || busy}
        onClick={() => void act('/advisor/dreaming/run')}
      >
        Dream now
      </button>
      {state && <p>{state.pending_review} awaiting review</p>}
      {error && <p role="alert">{error}</p>}
      {state?.jobs.map((job) => (
        <div key={job.id}>
          <p>
            {job.state}
            {job.reason && ` · ${job.reason}`}
          </p>
          {job.groups.map((group) => (
            <article key={group.operation_key}>
              {group.state === 'review' && group.note ? (
                <Review
                  group={group}
                  apply={async (note) => {
                    await act(
                      `/advisor/dreaming/${job.id}/${group.operation_key}/approve`,
                      'POST',
                      { note },
                    );
                  }}
                />
              ) : (
                <p>
                  {group.note?.title ?? 'Related memories'} · {group.state}
                </p>
              )}
              {group.state === 'review' && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      `/advisor/dreaming/${job.id}/${group.operation_key}/skip`,
                    )
                  }
                >
                  Keep separate
                </button>
              )}
              {group.state === 'committed' && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={async () => {
                    try {
                      const current = await api<MemoryNote>(
                        `/advisor/memory/${group.result_id}`,
                      );
                      await act(
                        `/advisor/dreaming/undo/${group.operation_key}`,
                        'POST',
                        { expected_revision: current.revision },
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Undo consolidation
                </button>
              )}
            </article>
          ))}
        </div>
      ))}
    </section>
  );
}
