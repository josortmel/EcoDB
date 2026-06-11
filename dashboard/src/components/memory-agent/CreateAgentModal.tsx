import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { ModalShell, Field, TextInput, SelectInput, PrimaryButton } from './ModalShell';
import { useCreateAgent } from '../../hooks/useMemoryAgent';

const COGNITION = ['narrative', 'work', 'mixed'];

export function CreateAgentModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const create = useCreateAgent();
  const [identifier, setIdentifier] = useState('');
  const [name, setName] = useState('');
  const [cognition, setCognition] = useState('narrative');
  const canSave = identifier.trim().length > 0 && !create.isPending;

  const submit = () =>
    create.mutate(
      { identifier: identifier.trim(), display_name: name.trim() || undefined, cognition_class: cognition },
      { onSuccess: () => { toast(t('ma.configs.agents.created')); onClose(); }, onError: (e) => toast(errMsg(e, t, t('ma.configs.common.actionFailed'))) },
    );

  return (
    <ModalShell
      title={t('ma.configs.agents.createTitle')}
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2.5">
          <button type="button" onClick={onClose} className="rounded-btn px-4 py-2 font-body text-[12.5px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.common.cancel')}</button>
          <PrimaryButton disabled={!canSave} onClick={submit}>{t('ma.configs.agents.save')}</PrimaryButton>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t('ma.configs.agents.identifier')}><TextInput value={identifier} onChange={setIdentifier} placeholder="Prima" maxLength={64} /></Field>
        <Field label={t('ma.configs.agents.displayName')}><TextInput value={name} onChange={setName} maxLength={80} /></Field>
        <Field label={t('ma.configs.agents.cognition')}>
          <SelectInput value={cognition} onChange={setCognition}>
            {COGNITION.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </SelectInput>
        </Field>
      </div>
    </ModalShell>
  );
}
