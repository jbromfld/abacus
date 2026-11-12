import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import Modal from './Modal';
import DreamingPanel from './DreamingPanel';

export type MemoryNote = {
  id?: string;
  revision?: number;
  title: string;
  text: string;
  kind: 'intention' | 'preference' | 'decision';
  source_date: string;
  source_excerpt: string;
  cues: string[];
  status: 'active' | 'completed' | 'abandoned';
  superseded_by?: string | null;
  consolidation?: {
    sources: MemoryNote[];
    operation_key: string;
    undone: boolean;
  } | null;
  history?: MemoryNote[];
};
export type MemoryRecall = {
  status: string;
  warnings: string[];
  epoch: string;
  notes: Pick<
    MemoryNote,
    'id' | 'revision' | 'title' | 'text' | 'kind' | 'source_date'
  >[];
};
export function memoryChanged() {
  window.dispatchEvent(new Event('abacus-memory-changed'));
  // Notify other open tabs without persisting private note/conversation contents.
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel('abacus-memory');
    channel.postMessage('changed');
    channel.close();
  }
}

function emptyNote(source = ''): MemoryNote {
  const today = new Date();
  return {
    title: '',
    text: '',
    kind: 'intention',
    source_date: `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
    source_excerpt: source.slice(0, 1000),
    cues: [],
    status: 'active',
  };
}

function NoteEditor({
  initial,
  exchange,
  onClose,
  onSaved,
}: {
  initial?: MemoryNote;
  exchange?: { user_message: string; assistant_message: string };
  onClose: () => void;
  onSaved: () => void;
}) {
  const [note, setNote] = useState(
    initial ?? emptyNote(exchange?.user_message),
  );
  const [cueText, setCueText] = useState(initial?.cues.join(', ') ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [similar, setSimilar] = useState<MemoryNote[]>([]);
  const [confirmForget, setConfirmForget] = useState(false);
  const createKey = useRef(crypto.randomUUID());
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const draftStarted = useRef(false);
  useEffect(() => {
    if (!exchange || draftStarted.current) return;
    draftStarted.current = true;
    setBusy(true);
    api<{ note: MemoryNote; warning: string }>(
      '/advisor/memory/draft',
      'POST',
      exchange,
    )
      .then((result) => {
        if (active.current) {
          setNote(result.note);
          setCueText(result.note.cues.join(', '));
          setWarning(result.warning);
        }
      })
      .catch((e) => {
        if (active.current) setError(e.message);
      })
      .finally(() => {
        if (active.current) setBusy(false);
      });
  }, [exchange]);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      if (active.current) setError((e as Error).message);
    } finally {
      if (active.current) setBusy(false);
    }
  };
  const fields = () => ({
    title: note.title,
    text: note.text,
    kind: note.kind,
    source_date: note.source_date,
    source_excerpt: note.source_excerpt,
    cues: cueText
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean),
    status: note.status,
  });
  const change = <K extends keyof MemoryNote>(key: K, value: MemoryNote[K]) =>
    setNote({ ...note, [key]: value });
  return (
    <Modal
      title={initial?.id ? 'Edit remembered note' : 'Remember this'}
      onClose={onClose}
    >
      <form
        className="memory-form"
        onSubmit={(event) => {
          event.preventDefault();
          void perform(async () => {
            if (note.id) {
              await api(`/advisor/memory/${note.id}`, 'PUT', {
                note: fields(),
                expected_revision: note.revision,
              });
              memoryChanged();
            } else {
              await api('/advisor/memory', 'POST', {
                note: fields(),
                create_key: createKey.current,
              });
            }
            if (active.current) onSaved();
          });
        }}
      >
        <p>
          Keep a dated statement you approve. An intention is not proof of
          savings and does not change your budget. Only this note and the source
          excerpt below are retained.
        </p>
        {exchange && (
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const result = await api<{ note: MemoryNote; warning: string }>(
                  '/advisor/memory/draft',
                  'POST',
                  exchange,
                );
                if (active.current) {
                  setNote(result.note);
                  setCueText(result.note.cues.join(', '));
                  setWarning(result.warning);
                }
              })
            }
          >
            Draft from this exchange
          </button>
        )}
        {warning && (
          <p className="notice" role="status">
            {warning}
          </p>
        )}
        <label>
          Title
          <input
            required
            maxLength={100}
            value={note.title}
            onChange={(e) => change('title', e.target.value)}
          />
        </label>
        <label>
          Note
          <textarea
            aria-label="Note"
            required
            maxLength={400}
            rows={4}
            value={note.text}
            onChange={(e) => change('text', e.target.value)}
          />
        </label>
        <label>
          Type
          <select
            value={note.kind}
            onChange={(e) =>
              change('kind', e.target.value as MemoryNote['kind'])
            }
          >
            <option value="intention">Intention</option>
            <option value="preference">Preference</option>
            <option value="decision">Decision</option>
          </select>
        </label>
        <label>
          Source date
          <input
            required
            type="date"
            value={note.source_date}
            onChange={(e) => change('source_date', e.target.value)}
          />
        </label>
        <label>
          Approved source excerpt
          <textarea
            aria-label="Approved source excerpt"
            maxLength={1000}
            rows={3}
            value={note.source_excerpt}
            onChange={(e) => change('source_excerpt', e.target.value)}
          />
        </label>
        <label>
          Topic cues (comma separated)
          <input
            maxLength={407}
            value={cueText}
            onChange={(e) => setCueText(e.target.value)}
          />
        </label>
        <label>
          Status
          <select
            value={note.status}
            onChange={(e) =>
              change('status', e.target.value as MemoryNote['status'])
            }
          >
            <option value="active">Active</option>
            <option value="completed">Completed</option>
            <option value="abandoned">Abandoned</option>
          </select>
        </label>
        {!note.id && (
          <button
            type="button"
            className="secondary"
            disabled={busy || !note.text.trim()}
            onClick={() =>
              void perform(async () => {
                const result = await api<{ items: MemoryNote[] }>(
                  '/advisor/memory/similar',
                  'POST',
                  { query: `${note.title} ${note.text}`.slice(0, 2000) },
                );
                if (active.current) setSimilar(result.items);
              })
            }
          >
            Check for similar notes
          </button>
        )}
        {similar.length > 0 && (
          <div className="notice">
            <p>
              Similar notes are not merged automatically. Choose an existing
              note to replace explicitly, or save a separate note.
            </p>
            {similar.map((item) => (
              <button
                type="button"
                className="secondary"
                key={item.id}
                disabled={busy}
                onClick={() =>
                  void perform(async () => {
                    const existing = await api<MemoryNote>(
                      `/advisor/memory/${item.id}`,
                    );
                    if (active.current) {
                      setNote({
                        ...note,
                        id: existing.id,
                        revision: existing.revision,
                        history: existing.history,
                      });
                      setSimilar([]);
                    }
                  })
                }
              >
                Replace “{item.title}” · {item.source_date}
              </button>
            ))}
          </div>
        )}
        {note.superseded_by && (
          <p className="notice">
            This source was superseded. Edit its consolidated memory or undo the
            consolidation.
          </p>
        )}
        {note.consolidation && (
          <details>
            <summary>Retained source memories</summary>
            {note.consolidation.sources.map((source) => (
              <article key={source.id}>
                <strong>
                  {source.title} · {source.source_date}
                </strong>
                <p>{source.text}</p>
                <blockquote>{source.source_excerpt}</blockquote>
              </article>
            ))}
          </details>
        )}
        {note.history && (
          <details>
            <summary>Earlier revisions ({note.history.length})</summary>
            {note.history.map((entry) => (
              <article key={entry.revision}>
                <strong>
                  Revision {entry.revision} · {entry.source_date}
                </strong>
                <p>{entry.text}</p>
                <blockquote>{entry.source_excerpt}</blockquote>
              </article>
            ))}
          </details>
        )}
        {error && (
          <p className="red" role="alert">
            {error}
          </p>
        )}
        <div className="button-group">
          <button disabled={busy || !!note.superseded_by}>
            {busy ? 'Working…' : note.id ? 'Save revision' : 'Save memory'}
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          {note.id && (
            <button
              type="button"
              className="secondary red"
              disabled={busy}
              onClick={() => setConfirmForget(true)}
            >
              Forget note
            </button>
          )}
        </div>
        {confirmForget && (
          <div className="notice">
            <p>
              Forget this note and its consolidated family, including all
              retained sources, revisions, and embeddings? Your current advisor
              conversation will be cleared. Older backups may retain it.
            </p>
            <button
              type="button"
              className="secondary red"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  try {
                    await api(
                      `/advisor/memory/${note.id}${note.consolidation || note.superseded_by ? '/family' : ''}?expected_revision=${note.revision}`,
                      'DELETE',
                    );
                  } finally {
                    // A timeout may follow a committed forget; clear stale context.
                    memoryChanged();
                  }
                  if (active.current) onSaved();
                })
              }
            >
              Confirm forget
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setConfirmForget(false)}
            >
              Keep note
            </button>
          </div>
        )}
      </form>
    </Modal>
  );
}

export function RememberExchange({
  user,
  assistant,
}: {
  user: string;
  assistant: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="text-button" onClick={() => setOpen(true)}>
        Remember this
      </button>
      {open && (
        <NoteEditor
          exchange={{ user_message: user, assistant_message: assistant }}
          onClose={() => setOpen(false)}
          onSaved={() => setOpen(false)}
        />
      )}
    </>
  );
}

export default function AdvisorMemory({
  enabled,
  revision = 0,
}: {
  enabled: boolean;
  revision?: number;
}) {
  const [status, setStatus] = useState('Advisor memory is off.');
  const [notes, setNotes] = useState<MemoryNote[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [editing, setEditing] = useState<MemoryNote | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const changed = () => setRefresh((value) => value + 1);
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
    setError('');
    setNotes([]);
    setNext(null);
    if (!enabled) {
      setStatus(
        'Advisor memory is off. Saved notes are retained until forgotten.',
      );
      return;
    }
    setLoading(true);
    Promise.all([
      api<{ message: string }>('/advisor/memory/status'),
      api<{ items: MemoryNote[]; next_offset: number | null }>(
        '/advisor/memory',
      ),
    ])
      .then(([state, result]) => {
        if (active) {
          setStatus(state.message);
          setNotes(result.items);
          setNext(result.next_offset);
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
    };
  }, [enabled, revision, refresh]);
  const edit = async (id: string) => {
    setError('');
    try {
      setEditing(await api<MemoryNote>(`/advisor/memory/${id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="panel memory-panel">
      <div className="section-head">
        <div>
          <h2>Advisor memory</h2>
          <p role="status">
            {loading ? 'Connecting to local Memora…' : status}
          </p>
        </div>
      </div>
      <div className="memory-content">
        <p>
          Approved intentions, preferences, and decisions stay local. Full
          conversations are not archived. Completed and abandoned notes are
          excluded from recall. After consolidation, only the combined note is
          listed; originals remain in its history.
        </p>
        {error && (
          <p className="red" role="alert">
            {error}
          </p>
        )}
        {enabled && (
          <>
            {enabled && <DreamingPanel />}
            <div className="button-group">
              <button
                className="secondary"
                onClick={() => setEditing(emptyNote())}
              >
                Add note manually
              </button>
              <button
                className="text-button"
                onClick={() => setRefresh((n) => n + 1)}
              >
                Refresh memory
              </button>
            </div>
            {!loading && !error && !notes.length && (
              <p>
                No approved notes yet. Use Remember this after an advisor
                exchange, or add a note manually.
              </p>
            )}
            {notes.map((note) => (
              <article className="memory-note" key={note.id}>
                <strong>{note.title}</strong>
                <small>
                  {note.source_date} · {note.kind} ·{' '}
                  {note.superseded_by ? 'superseded' : note.status}
                </small>
                <p>{note.text}</p>
                <button
                  className="text-button"
                  onClick={() => void edit(note.id!)}
                >
                  Edit “{note.title}”
                </button>
              </article>
            ))}
            {next !== null && (
              <button
                className="secondary"
                disabled={loading}
                onClick={async () => {
                  setLoading(true);
                  try {
                    const result = await api<{
                      items: MemoryNote[];
                      next_offset: number | null;
                    }>(`/advisor/memory?offset=${next}`);
                    setNotes([...notes, ...result.items]);
                    setNext(result.next_offset);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setLoading(false);
                  }
                }}
              >
                More notes
              </button>
            )}
          </>
        )}
      </div>
      {editing && enabled && (
        <NoteEditor
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setRefresh((n) => n + 1);
          }}
        />
      )}
    </section>
  );
}
