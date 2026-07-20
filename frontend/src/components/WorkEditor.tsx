import { FormEvent, useEffect, useMemo, useState } from 'react';
import type {
  CatalogField,
  SchemaDefinition,
  WorkDetail,
  WorkPatch,
} from '../api/types';
import { StatusBadge } from './StatusBadge';

interface Props {
  runId: string;
  work: WorkDetail | null;
  schemas: SchemaDefinition[];
  catalogFields: CatalogField[];
  saving: boolean;
  approving: boolean;
  onSave: (patch: WorkPatch) => Promise<void>;
  onApprove: () => Promise<void>;
}

type DraftFields = Record<string, string>;

const SOURCE_LABELS: Record<string, string> = {
  pdf: 'PDF',
  bibtex: 'BibTeX',
  ris: 'RIS',
};

function valuesToDraft(work: WorkDetail): DraftFields {
  return Object.fromEntries(
    work.fields.map((field) => [field.field_id, field.selected_values.join('\n')]),
  );
}

function fieldPayload(value: string, repeatable: boolean): string | string[] | null {
  const clean = value.trim();
  if (!clean) return null;
  if (!repeatable) return clean;
  return clean
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

function sourceName(value: string): string {
  const withoutRecord = value.split('#')[0];
  return withoutRecord.split(/[\\/]/).pop() || withoutRecord;
}

function physicalSourcePaths(values: string[]): string[] {
  return [...new Set(values.map((value) => value.split('#')[0]))];
}

function sourceUrl(runId: string, relativePath: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/source?path=${encodeURIComponent(relativePath)}`;
}

export function WorkEditor({
  runId,
  work,
  schemas,
  catalogFields,
  saving,
  approving,
  onSave,
  onApprove,
}: Props) {
  const [schemaId, setSchemaId] = useState<string>('');
  const [included, setIncluded] = useState(true);
  const [fields, setFields] = useState<DraftFields>({});
  const [baseline, setBaseline] = useState('');

  useEffect(() => {
    if (!work) return;
    const nextFields = valuesToDraft(work);
    setSchemaId(work.schema_id ?? '');
    setIncluded(work.included);
    setFields(nextFields);
    setBaseline(JSON.stringify({ schemaId: work.schema_id ?? '', included: work.included, nextFields }));
  }, [work]);

  const selectedSchema = schemas.find((schema) => schema.id === schemaId) ?? null;
  const fieldMap = useMemo(
    () => new Map(catalogFields.map((field) => [field.id, field])),
    [catalogFields],
  );
  const detailMap = useMemo(
    () => new Map((work?.fields ?? []).map((field) => [field.field_id, field])),
    [work],
  );
  const attentionByField = useMemo(() => {
    const grouped = new Map<string, WorkDetail['attention_items']>();
    for (const item of work?.attention_items ?? []) {
      if (!item.field_id) continue;
      const current = grouped.get(item.field_id) ?? [];
      current.push(item);
      grouped.set(item.field_id, current);
    }
    return grouped;
  }, [work]);
  const generalAttention = included
    ? (work?.attention_items ?? []).filter((item) => !item.field_id)
    : [];
  const dirty = Boolean(
    work && baseline !== JSON.stringify({ schemaId, included, nextFields: fields }),
  );

  if (!work) {
    return (
      <section className="card editor empty-state">
        Selecione uma referência para revisar os dados extraídos.
      </section>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!included) {
      await onSave({ included: false, fields: {} });
      return;
    }

    const payloadFields: Record<string, string | string[] | null> = {};
    for (const fieldId of selectedSchema?.ordered_fields ?? []) {
      const definition = fieldMap.get(fieldId);
      if (!definition) continue;
      payloadFields[fieldId] = fieldPayload(fields[fieldId] ?? '', definition.repeatable);
    }
    await onSave({
      schema_id: schemaId || null,
      included: true,
      fields: payloadFields,
    });
  }

  return (
    <section className="card editor">
      <div className="editor-header">
        <div>
          <div className="editor-status-line">
            <StatusBadge included={work.included} readiness={work.readiness} />
            {work.review_state === 'approved' && <span>Confirmada pelo usuário</span>}
          </div>
          <h2>{work.title || 'Título não identificado'}</h2>
          <div className="source-files">
            <span>Arquivos de origem:</span>
            {physicalSourcePaths(work.source_relative_paths).map((sourcePath) => (
              <a
                key={sourcePath}
                href={sourceUrl(runId, sourcePath)}
                target="_blank"
                rel="noreferrer"
                title={`Abrir ${sourcePath}`}
              >
                {sourceName(sourcePath)}
              </a>
            ))}
          </div>
          <div className="source-summary" title={work.source_relative_paths.join(', ')}>
            <span>Fontes usadas:</span>
            {work.source_types.map((sourceType) => (
              <strong className="source-chip" key={sourceType}>
                {SOURCE_LABELS[sourceType] ?? sourceType.toUpperCase()}
              </strong>
            ))}
          </div>
        </div>
      </div>

      {included ? (
        <div className="reference-preview">
          <span>Referência gerada</span>
          <p>{work.reference || 'A referência ainda não pode ser gerada.'}</p>
        </div>
      ) : (
        <div className="excluded-work-note">
          Esta obra não será incluída no arquivo final. Os dados extraídos ficam preservados caso você a inclua novamente.
        </div>
      )}

      {generalAttention.length > 0 && (
        <div className="issue-box">
          <strong>O que precisa ser conferido</strong>
          <ul>
            {generalAttention.map((item, index) => (
              <li key={`${item.code}-${index}`}>{item.message}</li>
            ))}
          </ul>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-grid two-columns">
          <label>
            <span>Tipo de referência</span>
            <select
              value={schemaId}
              disabled={!included}
              onChange={(event) => setSchemaId(event.target.value)}
            >
              <option value="">Selecione o esquema UFV</option>
              {schemas.map((schema) => (
                <option key={schema.id} value={schema.id}>
                  {schema.section} — {schema.label}
                </option>
              ))}
            </select>
          </label>
          <label className="include-toggle">
            <input
              type="checkbox"
              checked={included}
              onChange={(event) => setIncluded(event.target.checked)}
            />
            <span>Incluir no arquivo final</span>
          </label>
        </div>

        {included && (
          <div className="field-grid">
            {(selectedSchema?.ordered_fields ?? []).map((fieldId) => {
            const definition = fieldMap.get(fieldId);
            if (!definition) return null;
            const detail = detailMap.get(fieldId);
            const required = selectedSchema?.required_fields.includes(fieldId) ?? false;
            const fieldAttention = attentionByField.get(fieldId) ?? [];
            const hasError = fieldAttention.some((item) => item.severity === 'error');
            const alternatives = (detail?.alternatives ?? []).filter(
              (alternative) => alternative.values.join('\n') !== (fields[fieldId] ?? '').trim(),
            );
            return (
              <label
                className={`field-control ${fieldAttention.length ? 'field-needs-review' : ''} ${hasError ? 'field-has-error' : ''}`}
                key={fieldId}
              >
                <span className="field-label">
                  {definition.label} {required && <strong>*</strong>}
                  {fieldAttention.length > 0 && <em>Confira este campo</em>}
                </span>
                {definition.repeatable ? (
                  <textarea
                    rows={3}
                    value={fields[fieldId] ?? ''}
                    placeholder="Um valor por linha"
                    onChange={(event) =>
                      setFields((current) => ({ ...current, [fieldId]: event.target.value }))
                    }
                  />
                ) : (
                  <input
                    value={fields[fieldId] ?? ''}
                    onChange={(event) =>
                      setFields((current) => ({ ...current, [fieldId]: event.target.value }))
                    }
                  />
                )}

                {fieldAttention.map((item, index) => (
                  <small className={item.severity === 'error' ? 'field-error' : 'field-warning'} key={`${item.code}-${index}`}>
                    {item.message}
                  </small>
                ))}

                {alternatives.length > 0 && (
                  <div className="field-alternatives">
                    <span>Outros valores encontrados:</span>
                    {alternatives.map((alternative, index) => (
                      <button
                        type="button"
                        key={`${alternative.values.join('|')}-${index}`}
                        onClick={() =>
                          setFields((current) => ({
                            ...current,
                            [fieldId]: alternative.values.join('\n'),
                          }))
                        }
                      >
                        <strong>{alternative.values.join('; ')}</strong>
                        {alternative.sources.length > 0 && (
                          <small>{[...new Set(alternative.sources.map(sourceName))].join(', ')}</small>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {detail?.rule_summary && (
                  <details>
                    <summary>Ver regra UFV</summary>
                    <p>{detail.rule_summary}</p>
                    <p>{detail.rule_details}</p>
                  </details>
                )}
              </label>
            );
            })}
          </div>
        )}

        <div className="editor-actions">
          <div>{dirty ? 'Alterações ainda não salvas.' : ''}</div>
          <button
            type="button"
            className="button button-secondary"
            disabled={dirty || !work.can_approve || approving}
            onClick={() => void onApprove()}
          >
            {approving ? 'Confirmando…' : 'Confirmar referência'}
          </button>
          <button
            type="submit"
            className="button button-primary"
            disabled={!dirty || saving || (included && !schemaId)}
          >
            {saving ? 'Salvando…' : 'Salvar alterações'}
          </button>
        </div>
      </form>
    </section>
  );
}
