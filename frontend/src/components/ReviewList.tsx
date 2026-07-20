import type { WorkSummary } from '../api/types';
import { WORK_GROUP_ORDER, workGroupLabel } from '../domain/workGroups';
import { StatusBadge } from './StatusBadge';

const SOURCE_LABELS: Record<string, string> = { pdf: 'PDF', bibtex: 'BibTeX', ris: 'RIS' };

export type ReviewFilter = 'all' | 'ready' | 'review_required' | 'blocked' | 'excluded';

interface Props {
  works: WorkSummary[];
  selectedId: string | null;
  filter: ReviewFilter;
  onFilter: (filter: ReviewFilter) => void;
  onSelect: (workId: string) => void;
}

const tabs: Array<{ id: ReviewFilter; label: string }> = [
  { id: 'all', label: 'Todas' },
  { id: 'ready', label: 'Prontas' },
  { id: 'review_required', label: 'Revisar' },
  { id: 'blocked', label: 'Bloqueadas' },
  { id: 'excluded', label: 'Excluídas' },
];

function matches(work: WorkSummary, filter: ReviewFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'excluded') return !work.included;
  return work.included && work.readiness === filter;
}

export function ReviewList({ works, selectedId, filter, onFilter, onSelect }: Props) {
  const filtered = works.filter((work) => matches(work, filter));
  const count = (tab: ReviewFilter) => works.filter((work) => matches(work, tab)).length;
  const grouped = WORK_GROUP_ORDER.map((label) => ({
    label,
    works: filtered.filter((work) => workGroupLabel(work.schema_family) === label),
  })).filter((group) => group.works.length > 0);

  return (
    <aside className="review-list card" aria-label="Referências para revisão">
      <div className="section-heading review-heading">
        <div>
          <span className="eyebrow">Revisão</span>
          <h2>Referências</h2>
        </div>
      </div>
      <div className="filter-tabs" role="tablist" aria-label="Filtrar referências">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={filter === tab.id}
            className={filter === tab.id ? 'active' : ''}
            onClick={() => onFilter(tab.id)}
          >
            {tab.label} <span>{count(tab.id)}</span>
          </button>
        ))}
      </div>
      <div className="work-items">
        {grouped.map((group) => (
          <section className="work-group" key={group.label} aria-label={group.label}>
            <h3>{group.label}</h3>
            {group.works.map((work) => (
              <button
                key={work.work_id}
                className={`work-item ${selectedId === work.work_id ? 'selected' : ''}`}
                onClick={() => onSelect(work.work_id)}
              >
                <div className="work-item-top">
                  <StatusBadge included={work.included} readiness={work.readiness} />
                  <span>{work.manual_section ?? 'Tipo pendente'}</span>
                </div>
                <strong>{work.title || 'Título não identificado'}</strong>
                <small title={work.source_relative_path}>{work.source_relative_path}</small>
                <span className="work-source-types">
                  {work.source_types.map((item) => SOURCE_LABELS[item] ?? item.toUpperCase()).join(' + ')}
                </span>
              </button>
            ))}
          </section>
        ))}
        {filtered.length === 0 && (
          <div className="empty-state small">Nenhuma referência neste filtro.</div>
        )}
      </div>
    </aside>
  );
}
