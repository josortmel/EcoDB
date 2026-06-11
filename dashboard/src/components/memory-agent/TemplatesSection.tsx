import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { TemplateDrawer } from './TemplateDrawer';
import { useCellTemplates, type PromptTemplate } from '../../hooks/useMemoryAgent';

export function TemplatesSection() {
  const { t } = useTranslation();
  const q = useCellTemplates();
  const [open, setOpen] = useState(false);
  const [drawer, setDrawer] = useState<{ template: PromptTemplate | null } | null>(null);

  const templates = asArray<PromptTemplate>(q.data?.items);
  const hasTemplates = templates.length > 0;
  const bodyVisible = open || !hasTemplates;

  return (
    <div className="flex-none rounded-lg p-4" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={() => hasTemplates && setOpen((v) => !v)} className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">
          {hasTemplates && <span className="text-ink-3">{bodyVisible ? '▾' : '▸'}</span>}
          {t('ma.configs.templates.title')}
        </button>
        <button type="button" onClick={() => setDrawer({ template: null })} className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}>
          {t('ma.configs.templates.add')}
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
          ) : !hasTemplates ? (
            <p className="text-[12px] text-ink-3">{t('ma.configs.templates.empty')}</p>
          ) : (
            templates.map((tpl) => (
              <button key={tpl.id} type="button" onClick={() => setDrawer({ template: tpl })} className="flex items-center justify-between gap-3 rounded-md p-3 text-left transition-colors hover:bg-[var(--card-bg)]" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-ink-1">{tpl.name}</div>
                  <div className="mt-0.5 font-mono text-[9.5px] text-ink-3">{tpl.cell_type}</div>
                </div>
                {tpl.is_default && (
                  <span className="flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-2" style={{ background: 'color-mix(in srgb, var(--sec-memory-agent) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)' }}>
                    {t('ma.configs.templates.defaultBadge')}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      )}

      {drawer && <TemplateDrawer template={drawer.template} onClose={() => setDrawer(null)} onSaved={() => setOpen(true)} />}
    </div>
  );
}
