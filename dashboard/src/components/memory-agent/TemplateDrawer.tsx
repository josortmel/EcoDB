import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Toggle } from '../Toggle';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { MA_ACCENT } from './utils';
import { Field, TextInput } from './ModalShell';
import { useCreateTemplate, useUpdateTemplate, useDeleteTemplate, type PromptTemplate } from '../../hooks/useMemoryAgent';

// Right-side glass drawer editor for prompt templates (reuses the ClusterDrawer
// chrome). cell_type is only editable on create — the update endpoint takes
// name/content/is_default. Delete surfaces 409 (in-use) via errMsg.
export function TemplateDrawer({ template, onClose, onSaved }: { template: PromptTemplate | null; onClose: () => void; onSaved?: () => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const create = useCreateTemplate();
  const update = useUpdateTemplate();
  const del = useDeleteTemplate();
  const editing = !!template;

  const [name, setName] = useState(template?.name ?? '');
  const [cellType, setCellType] = useState(template?.cell_type ?? '');
  const [content, setContent] = useState((template?.content ?? '').slice(0, 20000));
  const [isDefault, setIsDefault] = useState(template?.is_default ?? false);
  const [confirm, setConfirm] = useState(false);
  const [contentFocused, setContentFocused] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const canSave = name.trim().length > 0 && content.trim().length > 0 && (editing || cellType.trim().length > 0) && !create.isPending && !update.isPending && !del.isPending;

  const save = () => {
    const done = () => { toast(t('ma.configs.templates.saved')); onSaved?.(); onClose(); };
    const onError = (e: unknown) => toast(errMsg(e, t, t('ma.configs.common.actionFailed')));
    if (editing && template) {
      update.mutate({ id: template.id, body: { name: name.trim(), content: content.trim(), is_default: isDefault } }, { onSuccess: done, onError });
    } else {
      create.mutate({ name: name.trim(), cell_type: cellType.trim(), content: content.trim(), is_default: isDefault }, { onSuccess: done, onError });
    }
  };

  const remove = () => {
    if (!template) return;
    del.mutate(template.id, { onSuccess: () => { toast(t('ma.configs.templates.deleted')); onClose(); }, onError: (e) => { setConfirm(false); toast(errMsg(e, t, t('ma.configs.common.actionFailed'))); } });
  };

  return (
    <>
      <div onClick={onClose} aria-hidden className="fixed inset-0 z-[60]" style={{ background: 'rgba(8,10,14,0.34)', backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)' }} />
      <aside role="dialog" aria-modal="true" className="fixed right-0 top-0 z-[61] flex h-screen w-[520px] max-w-[96vw] flex-col" style={{ background: 'var(--card-bg)', backdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)', WebkitBackdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)', boxShadow: '-1px 0 0 var(--card-edge) inset, -40px 0 70px -26px rgba(0,0,0,0.5)' }}>
        <div className="flex items-start justify-between gap-3 border-b border-[var(--card-hairline)] px-6 pb-4 pt-[22px]">
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-2">
              <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: MA_ACCENT, boxShadow: `0 0 8px ${MA_ACCENT}` }} />
              {t(editing ? 'ma.configs.templates.editTitle' : 'ma.configs.templates.addTitle')}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label={t('ma.configs.common.close')} className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={15} height={15}><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" /></svg>
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-6 py-4">
          <Field label={t('ma.configs.templates.name')}><TextInput value={name} onChange={setName} placeholder={t('ma.configs.templates.namePlaceholder')} maxLength={120} /></Field>
          {editing ? (
            <Field label={t('ma.configs.templates.cellType')}>
              <div className="rounded-[7px] px-2.5 py-2 font-mono text-[12px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{template?.cell_type}</div>
            </Field>
          ) : (
            <Field label={t('ma.configs.templates.cellType')}><TextInput value={cellType} onChange={setCellType} placeholder="consolidation" maxLength={64} /></Field>
          )}
          <label className="flex flex-1 flex-col gap-1.5">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.configs.templates.content')}</span>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onFocus={() => setContentFocused(true)}
              onBlur={() => setContentFocused(false)}
              placeholder={t('ma.configs.templates.contentPlaceholder')}
              maxLength={20000}
              className="min-h-[260px] flex-1 resize-y rounded-md px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink-1 outline-none placeholder:text-ink-4"
              style={{ background: 'var(--field-bg)', boxShadow: contentFocused ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)' : 'inset 0 0 0 1px var(--card-hairline)' }}
            />
          </label>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] text-ink-2">{t('ma.configs.templates.isDefault')}</span>
            <Toggle on={isDefault} onChange={setIsDefault} label={t('ma.configs.templates.isDefault')} />
          </div>
        </div>

        <div className="flex items-center gap-2.5 border-t border-[var(--card-hairline)] px-6 py-4">
          <button type="button" disabled={!canSave} onClick={save} className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-40" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}>{t('ma.configs.templates.save')}</button>
          {editing && (confirm ? (
            <>
              <button type="button" disabled={del.isPending} onClick={remove} className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-red disabled:opacity-50" style={{ background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}>{t('ma.configs.templates.deleteConfirm')}</button>
              <button type="button" onClick={() => setConfirm(false)} className="rounded-btn px-3 py-2.5 font-body text-[12.5px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.common.cancel')}</button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirm(true)} className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-red" style={{ background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}>{t('ma.configs.templates.delete')}</button>
          ))}
        </div>
      </aside>
    </>
  );
}
