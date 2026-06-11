import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { ModalShell, Field, TextInput, SelectInput, PrimaryButton } from './ModalShell';
import { CronBuilder } from './CronBuilder';
import {
  useCreateCellConfig,
  useUpdateCellConfig,
  type CellTaskConfig,
  type AgentSummary,
  type ProviderKey,
  type PromptTemplate,
  type ClusterLevel,
} from '../../hooks/useMemoryAgent';

const LEVELS: ClusterLevel[] = ['weekly', 'monthly', 'quarterly', 'yearly'];

export function ConfigEditModal({
  config,
  presetAgent,
  agents,
  providers,
  templates,
  onClose,
  onGoProviders,
}: {
  config?: CellTaskConfig | null;
  presetAgent?: string;
  agents: AgentSummary[];
  providers: ProviderKey[];
  templates: PromptTemplate[];
  onClose: () => void;
  onGoProviders: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const create = useCreateCellConfig();
  const update = useUpdateCellConfig();
  const editing = !!config;

  const [agent, setAgent] = useState(config?.agent_identifier ?? presetAgent ?? '');
  const [cellType, setCellType] = useState(config?.cell_type ?? '');
  const [provider, setProvider] = useState(config?.provider ?? '');
  const [model, setModel] = useState(config?.model ?? '');
  const [cron, setCron] = useState<string | null>(config?.schedule_cron ?? null);
  const [level, setLevel] = useState<string>(config?.level ?? '');
  const [templateId, setTemplateId] = useState<string>(config?.prompt_template_id != null ? String(config.prompt_template_id) : '');

  const noProviders = providers.length === 0;
  const modelsForProvider = providers.filter((p) => p.provider === provider && p.model_default).map((p) => p.model_default as string);
  // Provider drives the model — selecting a provider seeds its default model. Two
  // independent selects (no encoded composite key, so model names with spaces are
  // safe — VS_CF1/BC3_CFG).
  const onProvider = (v: string) => { setProvider(v); setModel(providers.find((p) => p.provider === v)?.model_default ?? ''); };
  const canSave = !!provider && !!model && (editing || (agent.trim().length > 0 && cellType.trim().length > 0)) && !create.isPending && !update.isPending;

  const submit = () => {
    const done = () => { toast(t('ma.configs.config.saved')); onClose(); };
    const onError = (e: unknown) => toast(errMsg(e, t, t('ma.configs.common.actionFailed')));
    if (editing && config) {
      update.mutate({ id: config.id, body: { model, provider, schedule_cron: cron, level: (level || null) as ClusterLevel | null, prompt_template_id: templateId ? Number(templateId) : null } }, { onSuccess: done, onError });
    } else {
      create.mutate({ agent_identifier: agent.trim(), cell_type: cellType.trim(), model, provider, schedule_cron: cron ?? undefined, level: (level || undefined) as ClusterLevel | undefined, prompt_template_id: templateId ? Number(templateId) : undefined, config: {} }, { onSuccess: done, onError });
    }
  };

  return (
    <ModalShell
      title={t(editing ? 'ma.configs.config.editTitle' : 'ma.configs.config.createTitle')}
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2.5">
          <button type="button" onClick={onClose} className="rounded-btn px-4 py-2 font-body text-[12.5px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.common.cancel')}</button>
          <PrimaryButton disabled={!canSave} onClick={submit}>{t('ma.configs.config.save')}</PrimaryButton>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        {editing ? (
          <Field label={t('ma.configs.config.agent')}>
            <div className="rounded-[7px] px-2.5 py-2 font-mono text-[12px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{config?.agent_identifier} · {config?.cell_type}</div>
          </Field>
        ) : (
          <>
            <Field label={t('ma.configs.config.agent')}>
              <SelectInput value={agent} onChange={setAgent}>
                <option value="">—</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.identifier}>{a.identifier}</option>
                ))}
              </SelectInput>
            </Field>
            <Field label={t('ma.configs.config.cellType')}><TextInput value={cellType} onChange={setCellType} placeholder={t('ma.configs.config.cellTypePlaceholder')} maxLength={64} /></Field>
          </>
        )}

        {noProviders ? (
          <Field label={t('ma.configs.config.model')}>
            <div className="flex items-center justify-between gap-2 rounded-[7px] px-2.5 py-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              <span className="text-[12px] text-ink-3">{t('ma.configs.config.addProviderFirst')}</span>
              <button type="button" onClick={onGoProviders} className="flex-none font-mono text-[11px] text-ink-1 underline underline-offset-2">{t('ma.configs.config.goToProviders')}</button>
            </div>
          </Field>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <Field label={t('ma.configs.config.provider')}>
              <SelectInput value={provider} onChange={onProvider}>
                <option value="">—</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.provider}>{p.provider}</option>
                ))}
              </SelectInput>
            </Field>
            <Field label={t('ma.configs.config.model')}>
              <SelectInput value={model} onChange={setModel}>
                <option value="">—</option>
                {modelsForProvider.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </SelectInput>
            </Field>
          </div>
        )}

        <Field label={t('ma.configs.config.schedule')}>
          <CronBuilder value={cron} onChange={setCron} />
        </Field>

        <Field label={t('ma.configs.config.level')}>
          <SelectInput value={level} onChange={setLevel}>
            <option value="">—</option>
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </SelectInput>
        </Field>

        <Field label={t('ma.configs.config.template')}>
          <SelectInput value={templateId} onChange={setTemplateId}>
            <option value="">{t('ma.configs.config.noTemplate')}</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={String(tpl.id)}>{tpl.name}</option>
            ))}
          </SelectInput>
        </Field>
      </div>
    </ModalShell>
  );
}
