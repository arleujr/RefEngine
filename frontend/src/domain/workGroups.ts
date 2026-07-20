export const WORK_GROUP_ORDER = [
  'Artigos e periódicos',
  'Livros, manuais e capítulos',
  'Teses, dissertações e TCCs',
  'Eventos e anais',
  'Patentes',
  'Documentos jurídicos',
  'Outros documentos',
] as const;

export type WorkGroupLabel = (typeof WORK_GROUP_ORDER)[number];

export function workGroupLabel(family: string | null): WorkGroupLabel {
  if (!family) return 'Outros documentos';
  if (family.startsWith('periodical') || family === 'newspaper_article') {
    return 'Artigos e periódicos';
  }
  if (family === 'monograph' || family === 'monograph_part') {
    return 'Livros, manuais e capítulos';
  }
  if (family === 'academic_work') return 'Teses, dissertações e TCCs';
  if (family.startsWith('event_')) return 'Eventos e anais';
  if (family === 'patent') return 'Patentes';
  if (family.startsWith('legal_') || family === 'civil_registry') {
    return 'Documentos jurídicos';
  }
  return 'Outros documentos';
}
