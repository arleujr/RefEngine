import type { InputInventory, Run, WorkSummary } from '../api/types';
import { WORK_GROUP_ORDER, workGroupLabel } from '../domain/workGroups';

interface Props {
  inventory: InputInventory | null;
  run: Run | null;
  works: WorkSummary[];
  loading: boolean;
  processing: boolean;
  onRefresh: () => void;
  onProcess: () => void;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

function resultSummary(run: Run | null): string {
  if (!run || !['review', 'published'].includes(run.status)) {
    return 'Após o processamento, arquivos do mesmo trabalho são reunidos para evitar referências duplicadas.';
  }

  const sourceWord = run.physical_sources === 1 ? 'arquivo' : 'arquivos';
  const workWord = run.selected_works === 1 ? 'trabalho único' : 'trabalhos únicos';
  const generated = run.ready_references + run.review_required_references;
  const referenceWord = generated === 1 ? 'referência gerada' : 'referências geradas';
  const blockedSuffix = run.blocked_references
    ? ` ${run.blocked_references} ${run.blocked_references === 1 ? 'item ainda está bloqueado' : 'itens ainda estão bloqueados'}.`
    : '';
  return `${run.physical_sources} ${sourceWord} resultaram em ${run.selected_works} ${workWord} e ${generated} ${referenceWord}.${blockedSuffix}`;
}

function typeDistribution(works: WorkSummary[]) {
  const counts = new Map<string, number>();
  for (const work of works) {
    const label = work.schema_family ? workGroupLabel(work.schema_family) : 'Tipo não identificado';
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const ordered: Array<{ label: string; count: number }> = WORK_GROUP_ORDER
    .map((label) => ({ label, count: counts.get(label) ?? 0 }))
    .filter((item) => item.count > 0);
  const unidentified = counts.get('Tipo não identificado') ?? 0;
  if (unidentified) ordered.push({ label: 'Tipo não identificado', count: unidentified });
  return ordered;
}

export function InputPanel({
  inventory,
  run,
  works,
  loading,
  processing,
  onRefresh,
  onProcess,
}: Props) {
  const total = inventory?.files.length ?? 0;
  const distribution = typeDistribution(works);
  const processed = Boolean(run && ['review', 'published'].includes(run.status));

  return (
    <section className="card input-card" aria-labelledby="input-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Entrada</span>
          <h2 id="input-title">Arquivos encontrados</h2>
        </div>
        <button className="button button-ghost" onClick={onRefresh} disabled={loading}>
          Atualizar lista
        </button>
      </div>

      <div className="folder-path" title={inventory?.input_directory}>
        {inventory?.input_directory ?? 'Carregando pasta input...'}
      </div>

      <div className="input-summary-grid">
        <div className="input-total-card">
          <strong>{total}</strong>
          <span>{total === 1 ? 'arquivo no input' : 'arquivos no input'}</span>
        </div>

        <div className="source-count-card" aria-label="Quantidade por formato">
          <div><span>PDF</span><strong>{inventory?.counts.pdf ?? 0}</strong></div>
          <div><span>BibTeX</span><strong>{inventory?.counts.bibtex ?? 0}</strong></div>
          <div><span>RIS</span><strong>{inventory?.counts.ris ?? 0}</strong></div>
        </div>

        <div className="deduplication-card">
          <strong>Resultado do processamento</strong>
          <p>{resultSummary(run)}</p>
          {processed && distribution.length > 0 && (
            <div className="work-type-counts" aria-label="Tipos de trabalhos identificados">
              {distribution.map((item) => (
                <div key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="file-list" aria-label="Arquivos na pasta input">
        {inventory?.files.map((file) => (
          <div className="file-row" key={file.relative_path}>
            <div>
              <strong>{file.relative_path}</strong>
              <span>{file.source_type.toUpperCase()}</span>
            </div>
            <span>{formatBytes(file.size_bytes)}</span>
          </div>
        ))}
        {!loading && total === 0 && (
          <div className="empty-state small">
            Coloque manualmente arquivos PDF, BibTeX (.bib ou .bibtex) ou RIS na pasta <code>input</code>.
          </div>
        )}
      </div>

      <button
        className="button button-primary button-wide"
        disabled={loading || processing || total === 0}
        onClick={onProcess}
      >
        {processing ? 'Processando referências…' : 'Processar referências'}
      </button>
    </section>
  );
}
