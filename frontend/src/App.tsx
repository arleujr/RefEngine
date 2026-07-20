import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api/client';
import type {
  CatalogField,
  InputInventory,
  PublishResponse,
  Run,
  SchemaDefinition,
  WorkDetail,
  WorkPatch,
  WorkSummary,
} from './api/types';
import { InputPanel } from './components/InputPanel';
import { PublishPanel } from './components/PublishPanel';
import { ReviewList, type ReviewFilter } from './components/ReviewList';
import { WorkEditor } from './components/WorkEditor';

export default function App() {
  const [inventory, setInventory] = useState<InputInventory | null>(null);
  const [schemas, setSchemas] = useState<SchemaDefinition[]>([]);
  const [catalogFields, setCatalogFields] = useState<CatalogField[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [works, setWorks] = useState<WorkSummary[]>([]);
  const [selectedWork, setSelectedWork] = useState<WorkDetail | null>(null);
  const [publication, setPublication] = useState<PublishResponse | null>(null);
  const [filter, setFilter] = useState<ReviewFilter>('all');
  const [busy, setBusy] = useState<string | null>('initial');
  const [error, setError] = useState<string | null>(null);

  const processing = run?.status === 'queued' || run?.status === 'processing';

  const refreshInventory = useCallback(async () => {
    try {
      setError(null);
      setInventory(await api.inventory());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível ler a pasta input.');
    }
  }, []);

  const loadWorks = useCallback(async (currentRun: Run) => {
    if (!['review', 'published'].includes(currentRun.status)) return;
    const nextWorks = await api.listWorks(currentRun.run_id);
    setWorks(nextWorks);

    if (nextWorks.length === 0) {
      setSelectedWork(null);
      return;
    }

    const preferred =
      nextWorks.find((item) => item.work_id === selectedWork?.work_id) ??
      nextWorks.find((item) => item.readiness !== 'ready') ??
      nextWorks[0];

    setSelectedWork(await api.getWork(currentRun.run_id, preferred.work_id));
  }, [selectedWork?.work_id]);

  useEffect(() => {
    void (async () => {
      try {
        const [nextInventory, nextSchemas, nextFields, runs] = await Promise.all([
          api.inventory(),
          api.schemas(),
          api.fields(),
          api.listRuns(),
        ]);

        setInventory(nextInventory);
        setSchemas(nextSchemas);
        setCatalogFields(nextFields);

        const latest = runs[0] ?? null;
        setRun(latest);

        if (latest && ['review', 'published'].includes(latest.status)) {
          await loadWorks(latest);
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'O RefEngine não pôde ser iniciado.');
      } finally {
        setBusy(null);
      }
    })();
  }, []); // Initial bootstrap only.

  useEffect(() => {
    if (!run || !processing) return;

    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const next = await api.getRun(run.run_id);
          setRun(next);

          if (!['queued', 'processing'].includes(next.status)) {
            window.clearInterval(timer);
            setBusy(null);

            if (next.status === 'failed') {
              setError(next.error_message || 'O processamento falhou.');
              return;
            }

            await loadWorks(next);
          }
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Falha ao acompanhar a execução.');
        }
      })();
    }, 1000);

    return () => window.clearInterval(timer);
  }, [run?.run_id, processing, loadWorks]);

  async function processInput() {
    try {
      setError(null);
      setPublication(null);
      setWorks([]);
      setSelectedWork(null);
      setBusy('processing');
      setRun(await api.createRun());
    } catch (cause) {
      setBusy(null);
      setError(cause instanceof Error ? cause.message : 'Não foi possível iniciar o processamento.');
    }
  }

  async function selectWork(workId: string) {
    if (!run) return;

    try {
      setBusy('work');
      setSelectedWork(await api.getWork(run.run_id, workId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível abrir a referência.');
    } finally {
      setBusy(null);
    }
  }

  async function saveWork(patch: WorkPatch) {
    if (!run || !selectedWork) return;

    try {
      setError(null);
      setBusy('save');

      const result = await api.saveWork(run.run_id, selectedWork.work_id, patch);
      setRun(result.run);
      setSelectedWork(result.work);
      setWorks(await api.listWorks(run.run_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a referência.');
      throw cause;
    } finally {
      setBusy(null);
    }
  }

  async function approveWork() {
    if (!run || !selectedWork) return;

    try {
      setError(null);
      setBusy('approve');

      const currentWorkId = selectedWork.work_id;
      const result = await api.approveWork(run.run_id, currentWorkId);
      const nextWorks = await api.listWorks(run.run_id);

      setRun(result.run);
      setWorks(nextWorks);

      const currentIndex = nextWorks.findIndex((item) => item.work_id === currentWorkId);
      const following = currentIndex >= 0
        ? [...nextWorks.slice(currentIndex + 1), ...nextWorks.slice(0, currentIndex)]
        : nextWorks;

      const nextPending = following.find(
        (item) => item.included && item.readiness !== 'ready',
      );

      if (nextPending) {
        setSelectedWork(await api.getWork(run.run_id, nextPending.work_id));
      } else {
        setFilter('all');
        setSelectedWork(result.work);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível confirmar a referência.');
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    if (!run) return;

    try {
      setError(null);
      setBusy('publish');

      const result = await api.publish(run.run_id);
      setRun(result.run);
      setPublication(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível gerar o arquivo final.');
    } finally {
      setBusy(null);
    }
  }

  const runStage = useMemo(() => {
    if (!run) return 'Aguardando arquivos';

    const labels: Record<Run['status'], string> = {
      queued: 'Execução na fila',
      processing: 'Extraindo e aplicando regras UFV',
      review: 'Revisão disponível',
      published: 'Arquivo final publicado',
      failed: 'Execução com falha',
    };

    return labels[run.status];
  }, [run]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <img src="/logo.png" alt="Logo da RefEngine" className="logo" />
    
        </div>

        <div className={`run-pill ${processing ? 'working' : ''}`}>{runStage}</div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="Fechar aviso">
            ×
          </button>
        </div>
      )}

      <main>
        <InputPanel
          inventory={inventory}
          run={run}
          works={works}
          loading={busy === 'initial'}
          processing={Boolean(processing || busy === 'processing')}
          onRefresh={() => void refreshInventory()}
          onProcess={() => void processInput()}
        />

        {processing && (
          <section className="card processing-card">
            <div className="spinner" aria-hidden="true" />
            <div>
              <strong>Processando os documentos do snapshot…</strong>
              <span>Extração, resolução de conflitos e aplicação do catálogo UFV 2025.</span>
            </div>
          </section>
        )}

        {run && ['review', 'published'].includes(run.status) && (
          <div className="review-layout">
            <ReviewList
              works={works}
              selectedId={selectedWork?.work_id ?? null}
              filter={filter}
              onFilter={setFilter}
              onSelect={(workId) => void selectWork(workId)}
            />

            <WorkEditor
              runId={run.run_id}
              work={selectedWork}
              schemas={schemas}
              catalogFields={catalogFields}
              saving={busy === 'save'}
              approving={busy === 'approve'}
              onSave={saveWork}
              onApprove={approveWork}
            />
          </div>
        )}

        <PublishPanel
          run={run}
          publishing={busy === 'publish'}
          publication={publication}
          onPublish={() => void publish()}
        />
      </main>

      <footer>
        RefEngine v1.0.0 · processamento 100% local · desenvolvido por Arleu Júnior
      </footer>
    </div>
  );
}