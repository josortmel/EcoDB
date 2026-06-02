import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { errMsg } from '../lib/errMsg';
import { useComposeStore } from '../stores/compose';
import { useToastStore } from '../stores/toast';
import { useMemoryPreview, useCreateMemory } from '../hooks/memory';

type TemplateId = 'meeting' | 'decision' | 'discovery';
type Visibility = 'public' | 'private';
interface FieldDef {
  key: string;
  required?: boolean;
  multiline?: boolean;
}
interface Template {
  id: TemplateId;
  type: string; // the resulting memory type (EcoDB type enum)
  fields: FieldDef[];
}

const TEMPLATES: Template[] = [
  { id: 'meeting', type: 'momento', fields: [{ key: 'topic', required: true }, { key: 'attendees' }, { key: 'notes', multiline: true }] },
  { id: 'decision', type: 'decision', fields: [{ key: 'decision', required: true, multiline: true }, { key: 'context', multiline: true }, { key: 'alternatives' }] },
  { id: 'discovery', type: 'descubrimiento', fields: [{ key: 'what', required: true, multiline: true }, { key: 'how' }, { key: 'implication', multiline: true }] },
];

const VIS: Visibility[] = ['public', 'private'];
const reduceMotionQuery = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

const fieldStyle = (focused: boolean) => ({
  background: 'var(--field-bg)',
  boxShadow: focused
    ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
    : 'inset 0 1px 3px var(--inset), inset 0 0 0 1px var(--card-hairline)',
});

function Field({ label, value, onChange, multiline, required }: { label: string; value: string; onChange: (v: string) => void; multiline?: boolean; required?: boolean }) {
  const [focused, setFocused] = useState(false);
  const cls = 'w-full rounded-md px-3 py-2 font-body text-[13px] text-ink-1 outline-none placeholder:text-ink-3';
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
        {label}
        {required && <span className="text-accent"> *</span>}
      </span>
      {multiline ? (
        <textarea value={value} onChange={(e) => onChange(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} rows={3} className={`${cls} resize-none`} style={fieldStyle(focused)} />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} className={cls} style={fieldStyle(focused)} />
      )}
    </label>
  );
}

function TemplateCard({ name, desc, onClick }: { name: string; desc: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="tpl-card"
      className="flex flex-col gap-1.5 rounded-lg p-4 text-left transition-colors hover:bg-[var(--inset)]"
      style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      <span className="text-[14px] font-semibold text-ink-1">{name}</span>
      <span className="text-[11.5px] leading-snug text-ink-3">{desc}</span>
    </button>
  );
}

function Chip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="rounded-[20px] px-3 py-1.5 font-mono text-[11px] transition-colors"
      style={active ? { color: 'var(--accent)', background: 'rgba(245,99,30,0.13)', boxShadow: 'inset 0 0 0 1px rgba(245,99,30,0.4)' } : { color: 'var(--ink-3)', background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      {label}
    </button>
  );
}

function Btn({ children, onClick, primary, disabled, testid }: { children: ReactNode; onClick: () => void; primary?: boolean; disabled?: boolean; testid?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={testid}
      className={`rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold transition-[filter] disabled:opacity-50 ${primary ? 'bg-btn-primary text-white hover:brightness-105' : 'text-ink-1'}`}
      style={primary ? { boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' } : { background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
    >
      {children}
    </button>
  );
}

function ModalInner({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const tx = t as (k: string, o?: Record<string, unknown>) => string;
  const toast = useToastStore((s) => s.show);
  const preview = useMemoryPreview();
  const create = useCreateMemory();

  const [step, setStep] = useState<'pick' | 'compose' | 'preview'>('pick');
  const [template, setTemplate] = useState<Template | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [content, setContent] = useState('');
  const [previewedContent, setPreviewedContent] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('public');
  const [tagsRaw, setTagsRaw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const [contentFocused, setContentFocused] = useState(false);

  const reduce = reduceMotionQuery?.matches ?? false;
  const data = preview.data;

  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Focus management (a11y): remember trigger, focus into the panel, restore on close.
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    triggerRef.current = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => panelRef.current?.querySelector<HTMLElement>('button, input, textarea')?.focus());
    return () => triggerRef.current?.focus?.();
  }, []);

  const onTrapKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== 'Tab' || !panelRef.current) return;
    const f = panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input, textarea, [tabindex]:not([tabindex="-1"])');
    if (f.length === 0) return;
    const first = f[0];
    const last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const assemble = (tpl: Template, vals: Record<string, string>): string =>
    tpl.fields
      .filter((f) => vals[f.key]?.trim())
      .map((f) => `${tx(`tpl.field.${f.key}`)}: ${vals[f.key].trim()}`)
      .join('\n');

  const pick = (tpl: Template) => {
    setTemplate(tpl);
    setFields({});
    setError(null);
    setStep('compose');
  };

  // populateContent only on the first preview (compose→preview). On re-preview we
  // must NOT overwrite the editable content — the user may keep typing while the
  // request is in flight (BC-1).
  const runPreview = (text: string, populateContent: boolean) => {
    setError(null);
    preview.mutate(text, {
      onSuccess: () => {
        if (populateContent) setContent(text);
        setPreviewedContent(text);
        setStep('preview');
      },
      onError: (e) => setError(errMsg(e, t, t('tpl.failed'))),
    });
  };

  const onPreview = () => {
    if (!template) return;
    const missing = template.fields.filter((f) => f.required && !fields[f.key]?.trim());
    if (missing.length) {
      setError(tx('tpl.missingFields', { fields: missing.map((f) => tx(`tpl.field.${f.key}`)).join(', ') }));
      return;
    }
    const text = assemble(template, fields);
    if (!text.trim()) {
      setError(t('tpl.needContent'));
      return;
    }
    runPreview(text, true);
  };

  const onCreate = () => {
    if (!template) return;
    setError(null);
    const tags = tagsRaw.split(',').map((s) => s.trim()).filter(Boolean);
    create.mutate(
      { content, type: template.type, visibility, tags: tags.length ? tags : undefined },
      {
        onSuccess: () => {
          toast(t('tpl.created'));
          onClose();
        },
        onError: (e) => setError(errMsg(e, t, t('tpl.failed'))),
      },
    );
  };

  const dirty = content.trim() !== previewedContent.trim();

  return (
    <div className="fixed inset-0 z-[90] flex items-start justify-center" onKeyDown={onTrapKeyDown}>
      <div
        onClick={onClose}
        aria-hidden
        className="absolute inset-0 transition-opacity duration-150"
        style={{ background: 'rgba(18,14,10,0.45)', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)', opacity: shown ? 1 : 0 }}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('tpl.title')}
        data-testid="template-modal"
        className="relative mt-[10vh] flex max-h-[80vh] w-[620px] max-w-[92vw] flex-col overflow-hidden rounded-xl transition-[opacity,transform] duration-150"
        style={{
          background: 'var(--card-bg)',
          backdropFilter: 'blur(var(--drawer-blur)) saturate(var(--palette-saturate))',
          WebkitBackdropFilter: 'blur(var(--drawer-blur)) saturate(var(--palette-saturate))',
          boxShadow: 'inset 0 0 0 1px var(--card-edge), 0 30px 80px -24px rgba(0,0,0,0.6)',
          opacity: shown ? 1 : 0,
          transform: reduce ? undefined : shown ? 'translateY(0)' : 'translateY(-8px)',
        }}
      >
        {/* header */}
        <div className="flex flex-none items-center justify-between gap-3 border-b border-[var(--card-hairline)] px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--accent)', boxShadow: '0 0 6px var(--accent)' }} />
            <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">{t('tpl.title')}</span>
            {template && <span className="font-mono text-[11px] text-ink-3">· {tx(`tpl.template.${template.id}.name`)}</span>}
          </div>
          <button type="button" onClick={onClose} aria-label={t('tpl.close')} className="grid h-[28px] w-[28px] place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={14} height={14}><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" /></svg>
          </button>
        </div>

        {/* body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <div className="mb-3 flex items-start gap-2 rounded-md px-3 py-2.5" style={{ background: 'color-mix(in srgb, var(--red) 10%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 30%, transparent)' }}>
              <span className="mt-[3px] h-[7px] w-[7px] flex-none rounded-full" style={{ background: 'var(--red)' }} />
              <span className="text-[12px] leading-relaxed text-ink-1">{error}</span>
            </div>
          )}

          {step === 'pick' && (
            <>
              <p className="mb-3 text-[12.5px] text-ink-3">{t('tpl.pickSubtitle')}</p>
              <div className="flex flex-col gap-2.5">
                {TEMPLATES.map((tpl) => (
                  <TemplateCard key={tpl.id} name={tx(`tpl.template.${tpl.id}.name`)} desc={tx(`tpl.template.${tpl.id}.desc`)} onClick={() => pick(tpl)} />
                ))}
              </div>
            </>
          )}

          {step === 'compose' && template && (
            <div className="flex flex-col gap-3.5">
              {template.fields.map((f) => (
                <Field key={f.key} label={tx(`tpl.field.${f.key}`)} value={fields[f.key] ?? ''} onChange={(v) => setFields((s) => ({ ...s, [f.key]: v }))} multiline={f.multiline} required={f.required} />
              ))}
              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('tpl.visibility')}</span>
                <div className="flex gap-1.5">
                  {VIS.map((v) => (
                    <Chip key={v} active={visibility === v} label={tx(`tpl.vis.${v}`)} onClick={() => setVisibility(v)} />
                  ))}
                </div>
              </div>
              <Field label={t('tpl.tags')} value={tagsRaw} onChange={setTagsRaw} />
            </div>
          )}

          {step === 'preview' && template && (
            <div className="flex flex-col gap-3.5">
              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('tpl.content')}</span>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  onFocus={() => setContentFocused(true)}
                  onBlur={() => setContentFocused(false)}
                  data-testid="tpl-content"
                  rows={4}
                  className="w-full resize-none rounded-md px-3 py-2 font-body text-[13px] leading-relaxed text-ink-1 outline-none"
                  style={fieldStyle(contentFocused)}
                />
              </label>

              <div>
                <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('tpl.entities')}</div>
                {(data?.entities?.length ?? 0) === 0 ? (
                  <div className="font-mono text-[11.5px] text-ink-3">{t('tpl.noEntities')}</div>
                ) : (
                  <div className="flex flex-wrap gap-1.5" data-testid="tpl-entities">
                    {data?.entities.map((e, i) => (
                      <span key={`${e.text}-${i}`} className="flex items-center gap-1.5 rounded-sm px-2 py-1 font-mono text-[10.5px] text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                        {e.text}
                        <span className="text-ink-3">{e.label}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {(data?.suggested_triples?.length ?? 0) > 0 && (
                <div>
                  <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('tpl.triples')}</div>
                  <div className="flex flex-col gap-1.5">
                    {data?.suggested_triples.map((tr, i) => (
                      <div key={i} className="flex items-center gap-2 font-mono text-[11px] text-ink-2">
                        <span className="text-ink-1">{tr.subject}</span>
                        <span className="rounded-sm px-1.5 py-0.5 text-[10px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{tr.predicate}</span>
                        <span className="text-ink-1">{tr.object}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* footer */}
        <div className="flex flex-none items-center justify-between gap-2 border-t border-[var(--card-hairline)] px-5 py-3.5">
          <div>
            {step === 'compose' && (
              <Btn onClick={() => setStep('pick')}>{t('tpl.back')}</Btn>
            )}
            {step === 'preview' && (
              <Btn onClick={() => setStep('compose')}>{t('tpl.back')}</Btn>
            )}
          </div>
          <div className="flex gap-2">
            {step === 'compose' && (
              <Btn primary onClick={onPreview} disabled={preview.isPending} testid="tpl-preview">
                {preview.isPending ? t('tpl.analyzing') : t('tpl.preview')}
              </Btn>
            )}
            {step === 'preview' && (
              <>
                {dirty && (
                  <Btn onClick={() => runPreview(content, false)} disabled={preview.isPending} testid="tpl-repreview">
                    {preview.isPending ? t('tpl.analyzing') : t('tpl.rePreview')}
                  </Btn>
                )}
                <Btn primary onClick={onCreate} disabled={create.isPending || preview.isPending || !content.trim()} testid="tpl-create">
                  {create.isPending ? t('tpl.creating') : t('tpl.create')}
                </Btn>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function TemplateModal() {
  const open = useComposeStore((s) => s.open);
  const close = useComposeStore((s) => s.closeCompose);
  if (!open) return null;
  return <ModalInner onClose={close} />;
}
