import type { PublishResponse, Run } from '../api/types';

interface Props {
  run: Run | null;
  publishing: boolean;
  publication: PublishResponse | null;
  onPublish: () => void;
}

export function PublishPanel({ run, publishing, publication, onPublish }: Props) {
  if (!run || !['review', 'published'].includes(run.status)) return null;
  const blocked = run.review_required_references + run.blocked_references > 0;
  const published = publication ?? (run.status === 'published' ? {
    run,
    references: run.ready_references,
    exports: {
      docx: `/api/v1/runs/${run.run_id}/exports/docx`,
      txt: `/api/v1/runs/${run.run_id}/exports/txt`,
    },
  } : null);

  return (
    <section className="card publish-card">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Publicação</span>
          <h2>Arquivo final</h2>
        </div>
      </div>

      <div className="metrics publish-metrics">
        <div><strong>{run.ready_references}</strong><span>prontas</span></div>
        <div><strong>{run.review_required_references}</strong><span>para revisar</span></div>
        <div><strong>{run.blocked_references}</strong><span>bloqueadas</span></div>
        <div><strong>{run.excluded_works}</strong><span>excluídas</span></div>
      </div>

      {published ? (
        <div className="download-box">
          <strong>Referências geradas com sucesso.</strong>
          <div>
            <a className="button button-primary" href={published.exports.docx}>Baixar DOCX</a>
            <a className="button button-secondary" href={published.exports.txt}>Baixar TXT</a>
          </div>
          <small>Uma cópia também está disponível em <code>output/latest</code>.</small>
        </div>
      ) : (
        <button
          className="button button-primary button-wide"
          disabled={blocked || publishing || run.ready_references === 0}
          onClick={onPublish}
        >
          {publishing ? 'Gerando arquivo final…' : 'Gerar referências finais'}
        </button>
      )}
      {blocked && !published && (
        <p className="blocking-note">Resolva ou exclua todas as referências pendentes antes de publicar.</p>
      )}
    </section>
  );
}
