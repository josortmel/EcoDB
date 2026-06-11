import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { ModalShell, Field, TextInput, PrimaryButton } from './ModalShell';
import { useProviders, useSaveProvider, useDeleteProvider, type ProviderKey } from '../../hooks/useMemoryAgent';

function ProviderCard({ p, onDelete, deleting }: { p: ProviderKey; onDelete: (id: number) => void; deleting: boolean }) {
  const { t } = useTranslation();
  const [confirm, setConfirm] = useState(false);
  return (
    <div className="flex items-center justify-between gap-3 rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="min-w-0">
        <div className="truncate text-[13px] text-ink-1">{p.display_name ?? p.provider}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
          <span>{p.provider}</span>
          <span>·</span>
          <span>{p.model_default ?? '—'}</span>
          <span>·</span>
          <span>{p.api_key_masked}</span>
        </div>
      </div>
      {confirm ? (
        <div className="flex flex-none gap-1.5">
          <button type="button" disabled={deleting} onClick={() => onDelete(p.id)} className="rounded-btn px-2.5 py-1 font-body text-[11px] font-semibold text-red disabled:opacity-50" style={{ background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}>{t('ma.configs.providers.delete')}</button>
          <button type="button" onClick={() => setConfirm(false)} className="rounded-btn px-2.5 py-1 font-body text-[11px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.common.cancel')}</button>
        </div>
      ) : (
        <button type="button" onClick={() => setConfirm(true)} className="flex-none font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 transition-colors hover:text-red">{t('ma.configs.providers.delete')}</button>
      )}
    </div>
  );
}

function AddProviderModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const save = useSaveProvider();
  const [provider, setProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [name, setName] = useState('');
  const [show, setShow] = useState(false);
  const canSave = provider.trim().length > 0 && apiKey.trim().length > 0 && !save.isPending;

  const submit = () =>
    save.mutate(
      { provider: provider.trim(), api_key: apiKey.trim(), model_default: model.trim() || undefined, display_name: name.trim() || undefined },
      { onSuccess: () => { toast(t('ma.configs.providers.saved')); onClose(); }, onError: (e) => toast(errMsg(e, t, t('ma.configs.common.actionFailed'))) },
    );

  return (
    <ModalShell
      title={t('ma.configs.providers.addTitle')}
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2.5">
          <button type="button" onClick={onClose} className="rounded-btn px-4 py-2 font-body text-[12.5px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.common.cancel')}</button>
          <PrimaryButton disabled={!canSave} onClick={submit}>{t('ma.configs.providers.save')}</PrimaryButton>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t('ma.configs.providers.provider')}><TextInput value={provider} onChange={setProvider} placeholder={t('ma.configs.providers.providerPlaceholder')} maxLength={64} /></Field>
        <Field label={t('ma.configs.providers.apiKey')}>
          <div className="flex gap-2">
            <input
              type={show ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={t('ma.configs.providers.apiKeyPlaceholder')}
              maxLength={400}
              className="min-w-0 flex-1 rounded-[7px] px-2.5 py-2 font-mono text-[12px] text-ink-1 outline-none placeholder:text-ink-4"
              style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
            />
            <button type="button" onClick={() => setShow((v) => !v)} className="flex-none rounded-[7px] px-2.5 font-mono text-[11px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              {show ? t('ma.configs.providers.hide') : t('ma.configs.providers.show')}
            </button>
          </div>
        </Field>
        <Field label={t('ma.configs.providers.modelDefault')}><TextInput value={model} onChange={setModel} placeholder={t('ma.configs.providers.modelPlaceholder')} maxLength={80} /></Field>
        <Field label={t('ma.configs.providers.displayName')}><TextInput value={name} onChange={setName} placeholder={t('ma.configs.providers.displayNamePlaceholder')} maxLength={80} /></Field>
      </div>
    </ModalShell>
  );
}

export function ProvidersSection() {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const q = useProviders();
  const del = useDeleteProvider();
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);

  const providers = asArray<ProviderKey>(q.data?.items);
  const hasProviders = providers.length > 0;
  const bodyVisible = open || !hasProviders;

  const onDelete = (id: number) =>
    del.mutate(id, { onSuccess: () => toast(t('ma.configs.providers.deleted')), onError: (e) => toast(errMsg(e, t, t('ma.configs.common.actionFailed'))) });

  return (
    <div className="flex-none rounded-lg p-4" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={() => hasProviders && setOpen((v) => !v)} className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">
          {hasProviders && <span className="text-ink-3">{bodyVisible ? '▾' : '▸'}</span>}
          {t('ma.configs.providers.title')}
        </button>
        <button type="button" onClick={() => setAdding(true)} className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}>
          {t('ma.configs.providers.add')}
        </button>
      </div>

      {bodyVisible && (
        <div className="mt-3 flex flex-col gap-2.5">
          {q.isError ? (
            <div className="flex items-center gap-2 rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 5px rgba(222,70,48,0.5)' }} />
              <span className="min-w-0 flex-1 text-[12px] text-ink-2">{errMsg(q.error, t, t('ma.configs.common.error'))}</span>
              <button type="button" onClick={() => void q.refetch()} className="flex-none font-mono text-[11px] text-ink-1 underline underline-offset-2">{t('ma.configs.common.retry')}</button>
            </div>
          ) : q.isPending ? (
            <div className="flex flex-col gap-2.5">
              {[0, 1].map((i) => (
                <span key={i} className="h-[46px] animate-pulse rounded-md" style={{ background: 'var(--inset)' }} />
              ))}
            </div>
          ) : (
            <>
              {!hasProviders && <p className="text-[12px] text-ink-3">{t('ma.configs.providers.hint')}</p>}
              {providers.map((p) => (
                <ProviderCard key={p.id} p={p} onDelete={onDelete} deleting={del.isPending && del.variables === p.id} />
              ))}
            </>
          )}
        </div>
      )}

      {adding && <AddProviderModal onClose={() => setAdding(false)} />}
    </div>
  );
}
