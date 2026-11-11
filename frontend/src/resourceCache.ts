import { useSyncExternalStore } from 'react';
// Request ownership stays with subscribers; aborting one screen cannot cancel
// another screen's read of the same resource.
type Entry = {
  promise: Promise<unknown>;
  controller: AbortController;
  users: number;
  settled: boolean;
  expires: number;
};
const reads = new Map<string, Entry>();
const listeners = new Set<() => void>();
const versions = new Map<string, number>();
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function useResourceRevision(roots: string[]) {
  return useSyncExternalStore(subscribe, () =>
    roots.reduce((total, root) => total + (versions.get(root) ?? 0), 0),
  );
}
export function invalidateResources(path: string, notify = true) {
  const root = path.split('?')[0].split('/')[1];
  const financial = [
    'transactions',
    'imports',
    'recurring',
    'annual-income',
    'planning',
    'savings',
    'categories',
  ].includes(root);
  const affected = [
    root,
    ...(financial
      ? [
          'transactions',
          'forecast',
          'forecasts',
          'trends',
          'spending',
          'expenses',
          'planning',
          'recurring',
          'accounts',
          'savings',
        ]
      : []),
  ];
  for (const key of reads.keys())
    if (affected.includes(key.split('?')[0].split('/')[1])) reads.delete(key);
  if (notify) {
    for (const root of new Set(affected))
      versions.set(root, (versions.get(root) ?? 0) + 1);
    listeners.forEach((listener) => listener());
  }
}
export function sharedRead<T>(
  path: string,
  signal: AbortSignal | undefined,
  fetcher: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  let entry = reads.get(path);
  if (!entry || entry.expires < Date.now()) {
    const controller = new AbortController();
    entry = {
      promise: Promise.resolve(),
      controller,
      users: 0,
      settled: false,
      expires: Date.now() + 30000,
    };
    const created = entry;
    created.promise = fetcher(controller.signal).then(
      (value) => {
        created.settled = true;
        return value;
      },
      (error) => {
        created.settled = true;
        if (reads.get(path) === created) reads.delete(path);
        throw error;
      },
    );
    reads.set(path, created);
  }
  const owned = entry;
  owned.users++;
  return new Promise<T>((resolve, reject) => {
    let done = false;
    const release = () => {
      if (done) return false;
      done = true;
      signal?.removeEventListener('abort', abort);
      owned.users--;
      if (!owned.users && !owned.settled) {
        if (reads.get(path) === owned) reads.delete(path);
        owned.controller.abort();
      }
      return true;
    };
    const abort = () => {
      if (release())
        reject(new DOMException('Request cancelled', 'AbortError'));
    };
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
    owned.promise.then(
      (value) => {
        if (release()) resolve(value as T);
      },
      (error) => {
        if (release()) reject(error);
      },
    );
  });
}
