import type { WorkSummary } from '../api/types';

type Props = Pick<WorkSummary, 'included' | 'readiness'>;

const labels = {
  ready: 'Pronta',
  review_required: 'Revisar',
  blocked: 'Bloqueada',
} as const;

export function StatusBadge({ included, readiness }: Props) {
  if (!included) {
    return <span className="status-badge status-excluded">Excluída</span>;
  }
  return (
    <span className={`status-badge status-${readiness}`}>
      {labels[readiness]}
    </span>
  );
}
