import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel, PanelState } from '../Panel';
import { asArray } from '../../lib/asArray';
import { MA_ACCENT } from './utils';
import { ProvidersSection } from './ProvidersSection';
import { TemplatesSection } from './TemplatesSection';
import { AgentConfigRow } from './AgentConfigRow';
import { CreateAgentModal } from './CreateAgentModal';
import { ConfigEditModal } from './ConfigEditModal';
import { useAgents, useProviders, useCellTemplates, type AgentSummary, type CellTaskConfig, type ProviderKey, type PromptTemplate } from '../../hooks/useMemoryAgent';

type ConfigModal = { config: CellTaskConfig | null; presetAgent?: string };

// Configs tab (Spec §5 Tab 2) — LLM providers (prerequisite) + per-agent cell
// worker configs. All endpoints are mocked until Hilo ships T2/T3/T4 + LLM keys;
// the trigger button hits the real endpoint. Provider edit needs a backend
// update hook (not in the mock contract) — add + delete only for now.
export function ConfigsTab() {
  const { t } = useTranslation();
  const agentsQ = useAgents();
  const providersQ = useProviders();
  const templatesQ = useCellTemplates();

  const agents = asArray<AgentSummary>(agentsQ.data?.items);
  const providers = asArray<ProviderKey>(providersQ.data?.items);
  const templates = asArray<PromptTemplate>(templatesQ.data?.items);

  const [creatingAgent, setCreatingAgent] = useState(false);
  const [configModal, setConfigModal] = useState<ConfigModal | null>(null);

  const headerControl = useMemo(
    () => (
      <div className="flex gap-2">
        <button type="button" onClick={() => setConfigModal({ config: null })} className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.config.newConfig')}</button>
        <button type="button" onClick={() => setCreatingAgent(true)} className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.agents.create')}</button>
      </div>
    ),
    [t],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-2">
      <ProvidersSection />
      <TemplatesSection />

      <Panel title={t('ma.configs.agents.title')} accent={MA_ACCENT} control={headerControl} className="flex-none">
        <PanelState loading={agentsQ.isPending} error={agentsQ.isError} onRetry={() => void agentsQ.refetch()} empty={!agentsQ.isPending && agents.length === 0} emptyLabel={t('ma.configs.agents.empty')}>
          <div className="flex flex-col gap-2.5">
            {agents.map((a) => (
              <AgentConfigRow
                key={a.id}
                agent={a}
                onEditConfig={(c) => setConfigModal({ config: c })}
                onNewConfig={(agentIdentifier) => setConfigModal({ config: null, presetAgent: agentIdentifier })}
              />
            ))}
          </div>
        </PanelState>
      </Panel>

      {creatingAgent && <CreateAgentModal onClose={() => setCreatingAgent(false)} />}
      {configModal && (
        <ConfigEditModal
          config={configModal.config}
          presetAgent={configModal.presetAgent}
          agents={agents}
          providers={providers}
          templates={templates}
          onClose={() => setConfigModal(null)}
          onGoProviders={() => setConfigModal(null)}
        />
      )}
    </div>
  );
}
