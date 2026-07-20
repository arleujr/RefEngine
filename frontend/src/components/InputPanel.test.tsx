import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { InputPanel } from './InputPanel';
import type { InputInventory, Run, WorkSummary } from '../api/types';

const inventory: InputInventory = {
  input_directory: 'C:/RefEngine/input',
  fingerprint: 'abc',
  total_bytes: 200,
  counts: { pdf: 2, bibtex: 1, ris: 1 },
  files: [
    { relative_path: 'article.pdf', source_type: 'pdf', size_bytes: 100, sha256: 'a' },
    { relative_path: 'book.pdf', source_type: 'pdf', size_bytes: 100, sha256: 'b' },
  ],
};

const run: Run = {
  run_id: 'run-1',
  status: 'review',
  created_at: '2026-07-15T12:00:00',
  started_at: '2026-07-15T12:00:01',
  finished_at: '2026-07-15T12:00:02',
  published_at: null,
  access_date: '2026-07-15',
  physical_sources: 4,
  selected_works: 3,
  ready_references: 1,
  review_required_references: 1,
  blocked_references: 1,
  excluded_works: 0,
  revision: 1,
  error_message: null,
};

function work(id: string, family: string | null): WorkSummary {
  return {
    work_id: id,
    source_file: `${id}.pdf`,
    source_files: [`${id}.pdf`],
    source_relative_path: `${id}.pdf`,
    source_relative_paths: [`${id}.pdf`],
    schema_id: family ? 'ufv.22' : null,
    schema_label: family ? 'Modelo' : null,
    schema_family: family,
    manual_section: family ? '5.12.22' : null,
    title: id,
    readiness: family ? 'ready' : 'blocked',
    review_state: 'pending',
    included: true,
    reference: family ? 'Referência.' : null,
    issues: [],
    source_types: ['pdf'],
  };
}

test('shows physical files, unique works, generated references and work types', () => {
  render(
    <InputPanel
      inventory={inventory}
      run={run}
      works={[
        work('article', 'periodical_article'),
        work('book', 'monograph'),
        work('unknown', null),
      ]}
      loading={false}
      processing={false}
      onRefresh={vi.fn()}
      onProcess={vi.fn()}
    />,
  );

  expect(screen.getByText(/4 arquivos resultaram em 3 trabalhos únicos/i)).toBeInTheDocument();
  expect(screen.getByText(/2 referências geradas/i)).toBeInTheDocument();
  expect(screen.getByText('Artigos e periódicos')).toBeInTheDocument();
  expect(screen.getByText('Livros, manuais e capítulos')).toBeInTheDocument();
  expect(screen.getByText('Tipo não identificado')).toBeInTheDocument();
});
