import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { WorkEditor } from './WorkEditor';
import type { CatalogField, SchemaDefinition, WorkDetail } from '../api/types';


afterEach(() => cleanup());

const schema: SchemaDefinition = {
  id: 'ufv.22',
  section: '5.12.22',
  printed_page: 97,
  label: 'Artigo em meio eletrônico',
  family: 'journal_article',
  medium: 'electronic',
  required_fields: ['title'],
  conditional_fields: [],
  ordered_fields: ['title'],
  pattern: '{title}',
  notes: [],
};

const field: CatalogField = {
  id: 'title',
  label: 'Título principal',
  repeatable: false,
  value_type: 'text',
};

const work = {
  work_id: 'abc',
  source_file: 'article.pdf',
  source_files: ['article.pdf'],
  source_relative_path: 'papers/article.pdf',
  source_relative_paths: ['papers/article.pdf'],
  schema_id: 'ufv.22',
  schema_label: schema.label,
  schema_family: schema.family,
  manual_section: schema.section,
  title: 'Título original',
  readiness: 'ready',
  review_state: 'pending',
  included: true,
  reference: 'TÍTULO ORIGINAL.',
  issues: [],
  source_types: ['pdf', 'bibtex'],
  schema,
  fields: [{
    field_id: 'title',
    label: field.label,
    repeatable: false,
    value_type: 'text',
    requirement: 'required',
    selected_values: ['Título original'],
    resolution_status: 'selected',
    confidence: 0.9,
    reason: 'Extraído do documento.',
    selected_sources: ['article.pdf'],
    alternatives: [],
    rule_summary: 'Título obrigatório.',
    rule_details: 'Regra detalhada.',
  }],
  missing_required_fields: [],
  conflicting_fields: [],
  can_approve: true,
  correction_suggestions: [],
  attention_items: [],
  processing_error: null,
} satisfies WorkDetail;

test('editing stays local and PATCH is represented only by the explicit save action', async () => {
  const user = userEvent.setup();
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <WorkEditor
      runId="run-1"
      work={work}
      schemas={[schema]}
      catalogFields={[field]}
      saving={false}
      approving={false}
      onSave={onSave}
      onApprove={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  const input = screen.getByDisplayValue('Título original');
  await user.clear(input);
  await user.type(input, 'Título revisado');
  expect(onSave).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Salvar alterações' }));
  expect(onSave).toHaveBeenCalledTimes(1);
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    fields: expect.objectContaining({ title: 'Título revisado' }),
  }));
});


test('technical confidence and backend synchronization text are not shown to the user', () => {
  render(
    <WorkEditor
      runId="run-1"
      work={work}
      schemas={[schema]}
      catalogFields={[field]}
      saving={false}
      approving={false}
      onSave={vi.fn().mockResolvedValue(undefined)}
      onApprove={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  expect(screen.queryByText(/confiança/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Highest source-backed score/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Dados sincronizados com o backend/i)).not.toBeInTheDocument();
  expect(screen.getAllByText('BibTeX').length).toBeGreaterThan(0);
});


test('source filename is a clickable link to the immutable run snapshot', () => {
  render(
    <WorkEditor
      runId="run-1"
      work={work}
      schemas={[schema]}
      catalogFields={[field]}
      saving={false}
      approving={false}
      onSave={vi.fn().mockResolvedValue(undefined)}
      onApprove={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  const links = screen.getAllByRole('link', { name: 'article.pdf' });
  const link = links[links.length - 1];
  expect(link).toHaveAttribute(
    'href',
    '/api/v1/runs/run-1/source?path=papers%2Farticle.pdf',
  );
  expect(link).toHaveAttribute('target', '_blank');
});

test('excluding a work saves without schema or mandatory field validation', async () => {
  const user = userEvent.setup();
  const onSave = vi.fn().mockResolvedValue(undefined);
  const blockedWork: WorkDetail = {
    ...work,
    schema_id: null,
    schema_label: null,
    schema_family: null,
    manual_section: null,
    schema: null,
    reference: null,
    readiness: 'blocked',
    fields: [],
    missing_required_fields: ['title'],
    can_approve: false,
    attention_items: [{
      code: 'REFERENCE_SCHEMA_NOT_IDENTIFIED',
      severity: 'error',
      message: 'Selecione o modelo UFV correto.',
      field_id: null,
      field_label: null,
    }],
  };

  render(
    <WorkEditor
      runId="run-1"
      work={blockedWork}
      schemas={[schema]}
      catalogFields={[field]}
      saving={false}
      approving={false}
      onSave={onSave}
      onApprove={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  await user.click(screen.getByRole('checkbox', { name: 'Incluir no arquivo final' }));
  expect(screen.queryByText('Selecione o modelo UFV correto.')).not.toBeInTheDocument();
  expect(screen.getByText(/não será incluída no arquivo final/i)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Salvar alterações' }));
  expect(onSave).toHaveBeenCalledWith({ included: false, fields: {} });
});
