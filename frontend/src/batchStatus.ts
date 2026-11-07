import type { ImportJob, ImportUpdate } from './api.ts';

export function syncImportUpdate<T extends { job?: ImportJob }>(
  items: T[],
  update: ImportUpdate | null,
): T[] {
  if (!update || !items.some((item) => item.job?.id === update.id))
    return items;
  return items.map((item) =>
    item.job?.id === update.id
      ? { ...item, job: { ...item.job, status: update.status } }
      : item,
  );
}

export function importStage(status: string) {
  switch (status) {
    case 'committed':
      return { label: 'Saved', action: 'View', saved: true };
    case 'undone':
      return { label: 'Undone', action: 'View', saved: false };
    case 'deleted':
      return { label: 'Deleted', action: null, saved: false };
    case 'processing':
      return { label: 'Extracting…', action: 'View', saved: false };
    case 'review':
      return {
        label: 'Ready to review / save',
        action: 'Continue',
        saved: false,
      };
    case 'failed':
      return { label: 'Needs attention', action: 'Review', saved: false };
    case 'interrupted':
      return { label: 'Interrupted', action: 'Review', saved: false };
    default:
      return { label: 'Prepared for review', action: 'Review', saved: false };
  }
}
