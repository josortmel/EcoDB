import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel, PanelState } from '../components/Panel';
import { Toggle } from '../components/Toggle';
import { useAuthMe } from '../hooks/auth';
import { useApiKeys, useRotateKey, type ApiKey } from '../hooks/settings';
import { ApiError } from '../lib/api';
import { asArray } from '../lib/asArray';
import { useToastStore } from '../stores/toast';
import { StopEntitiesPanel } from '../components/SettingsAdmin';

const SETTINGS_ACCENT = 'var(--sec-settings)';

// Display-only structures (no read endpoint yet — confirmed at 6.25b).
const TRUST_TIERS = [
  { tier: 'high', decay: '0.5%/day' },
  { tier: 'medium', decay: '1%/day' },
  { tier: 'low', decay: '2%/day' },
];
const FLAGS = ['bm25_search', 'contradiction_detection', 'auto_clustering'] as const;

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[var(--card-hairline)] py-2.5 last:border-0">
      <span className="font-mono text-[12.5px] text-ink-1">{label}</span>
      <span className="font-mono text-[11px] text-ink-3">{value}</span>
    </div>
  );
}

function ApiKeyManagement() {
  const { t } = useTranslation();
  const keys = useApiKeys();
  const rotate = useRotateKey();
  const [revealed, setRevealed] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Listing keys is admin-only; a non-admin gets 403. That's not an error to
  // retry — show the access note. (A user manages their own key via rotate, not
  // by hard-gating this whole panel behind isAdmin.)
  const is403 = keys.error instanceof ApiError && keys.error.status === 403;

  const onRotate = (id: number) =>
    rotate.mutate(id, {
      onSuccess: (res) => {
        setRevealed(res.new_api_key);
        setCopied(false);
      },
    });

  const copy = () => {
    if (revealed) void navigator.clipboard?.writeText(revealed)?.then(() => setCopied(true))?.catch(() => {});
  };

  return (
    <Panel title={t('set.apiKeys.title')} accent={SETTINGS_ACCENT} tag="v0.9">
      {is403 ? (
        <div className="grid place-items-center py-6 text-center font-mono text-[12px] text-ink-3">{t('set.limitedAccess')}</div>
      ) : (
      <PanelState
        loading={keys.isPending}
        error={keys.isError}
        onRetry={() => void keys.refetch()}
        empty={asArray(keys.data).length === 0}
        emptyLabel={t('set.apiKeys.none')}
      >
        {revealed && (
          <div
            className="mb-3 flex flex-col gap-2 rounded-md p-3"
            style={{ background: 'rgba(245,99,30,0.08)', boxShadow: 'inset 0 0 0 1px rgba(245,99,30,0.3)' }}
          >
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-accent">{t('set.apiKeys.shownOnce')}</div>
            <code className="select-all break-all font-mono text-[12px] text-ink-1">{revealed}</code>
            <div className="flex gap-2">
              <button type="button" onClick={copy} className="rounded-sm px-2.5 py-1 font-mono text-[11px] text-accent" style={{ background: 'rgba(245,99,30,0.13)' }}>
                {copied ? t('set.apiKeys.copied') : t('set.apiKeys.copy')}
              </button>
              <button
                type="button"
                onClick={() => {
                  // If we put the key on the OS clipboard, clear it on dismiss (adv-seg LOW).
                  if (copied) void navigator.clipboard?.writeText('')?.catch(() => {});
                  setRevealed(null);
                }}
                className="rounded-sm px-2.5 py-1 font-mono text-[11px] text-ink-3"
              >
                {t('set.apiKeys.dismiss')}
              </button>
            </div>
          </div>
        )}
        <div className="flex flex-col">
          {asArray<ApiKey>(keys.data).map((k) => (
            <div key={k.id} className="flex items-center gap-3 border-b border-[var(--card-hairline)] py-2.5 last:border-0">
              <span className="flex-1 font-mono text-[12.5px] text-ink-1">{k.name}</span>
              <span className="font-mono text-[10px]" style={{ color: k.active ? 'var(--grn)' : 'var(--ink-4)' }}>
                {k.active ? t('set.apiKeys.active') : t('set.apiKeys.inactive')}
              </span>
              <button
                type="button"
                onClick={() => onRotate(k.id)}
                disabled={rotate.isPending}
                className="rounded-sm px-2.5 py-1 font-mono text-[11px] text-ink-2 disabled:opacity-50"
                style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
              >
                {t('set.apiKeys.rotate')}
              </button>
              <button
                type="button"
                disabled
                aria-disabled
                title={t('set.requiresBackend')}
                className="rounded-sm px-2.5 py-1 font-mono text-[11px] text-red opacity-40"
              >
                {t('set.apiKeys.revoke')}
              </button>
            </div>
          ))}
        </div>
      </PanelState>
      )}
    </Panel>
  );
}

// #41 — the API base URL is configurable so EcoDB can point at a remote server,
// not just localhost. Plain config (no secret); the change needs a restart to
// re-issue the CSP/connect-src. Visible to everyone (a user must be able to set
// their own server), not admin-gated.
function ConnectionPanel() {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const [url, setUrl] = useState('');
  const [dirty, setDirty] = useState(false);
  const [focused, setFocused] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    void window.ecodb?.getConfig?.().then((c) => setUrl(c.apiBaseUrl)).catch(() => {});
  }, []);
  const trimmed = url.trim();
  const valid = /^https?:\/\/[^/\s]+/i.test(trimmed);
  const onSave = async () => {
    setSaving(true);
    try {
      const r = await window.ecodb.setConfig({ apiBaseUrl: trimmed });
      if (r.ok) {
        setDirty(false);
        toast(t('set.conn.saved'));
      } else {
        toast(t('set.conn.invalid'));
      }
    } catch {
      toast(t('set.conn.invalid'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Panel title={t('set.conn.title')} accent={SETTINGS_ACCENT}>
      <label className="block">
        <span className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{t('set.conn.urlLabel')}</span>
        <input
          type="text"
          value={url}
          spellCheck={false}
          onChange={(e) => {
            setUrl(e.target.value);
            setDirty(true);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={t('set.conn.placeholder')}
          className="w-full rounded-md px-3 py-2 font-mono text-[12.5px] text-ink-1 outline-none"
          style={{
            background: 'var(--field-bg)',
            boxShadow: focused
              ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
              : 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)',
          }}
        />
      </label>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-3">{t('set.conn.hint')}</p>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void onSave()}
          disabled={!valid || !dirty || saving}
          className="rounded-btn bg-btn-primary px-4 py-2 font-body text-[12px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
          style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}
        >
          {t('set.conn.save')}
        </button>
        <span className="font-mono text-[10.5px] text-ink-3">{t('set.conn.restart')}</span>
      </div>
    </Panel>
  );
}

export function Settings() {
  const { t } = useTranslation();
  const me = useAuthMe();
  const isAdmin = Boolean(me.data?.is_super || me.data?.is_ceo);
  // Display-only: there is no flags write endpoint yet, so the toggles are
  // disabled (no misleading "it saved" affordance — same rule as bin/revoke).
  const flags: Record<string, boolean> = { bm25_search: true, contradiction_detection: true, auto_clustering: false };

  return (
    <>
      <div className="mb-[18px] mt-1.5 px-0.5">
        <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('set.title')}</h1>
        <p className="mt-1.5 text-[12.5px] text-ink-3">{t('set.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <ConnectionPanel />
        <ApiKeyManagement />

        {isAdmin ? (
          <Panel title={t('set.trust.title')} accent={SETTINGS_ACCENT}>
            {TRUST_TIERS.map((tt) => (
              <Row key={tt.tier} label={t(`set.trust.${tt.tier}` as 'set.trust.high')} value={tt.decay} />
            ))}
          </Panel>
        ) : (
          <Panel title={t('set.trust.title')} accent={SETTINGS_ACCENT}>
            <div className="grid place-items-center py-6 font-mono text-[12px] text-ink-3">{t('set.limitedAccess')}</div>
          </Panel>
        )}

        {isAdmin && (
          <Panel title={t('set.flags.title')} accent={SETTINGS_ACCENT} tag={t('set.requiresBackend')}>
            <div className="flex flex-col">
              {FLAGS.map((f) => (
                <div
                  key={f}
                  title={t('set.requiresBackend')}
                  className="flex items-center justify-between gap-3 border-b border-[var(--card-hairline)] py-2.5 last:border-0"
                >
                  <span className="font-mono text-[12.5px] text-ink-1">{f.replace(/_/g, ' ')}</span>
                  <Toggle on={flags[f]} onChange={() => {}} label={f} disabled />
                </div>
              ))}
            </div>
          </Panel>
        )}

        {isAdmin && (
          <Panel title={t('set.watchdog.title')} accent={SETTINGS_ACCENT} tag="docker">
            <div className="grid place-items-center py-6 text-center font-mono text-[11px] leading-relaxed text-ink-3">
              {t('set.watchdog.note')}
            </div>
          </Panel>
        )}

        {isAdmin && <StopEntitiesPanel />}
      </div>

      <div
        className="mt-4 flex items-start gap-2.5 rounded-md px-4 py-3"
        style={{ background: 'color-mix(in srgb, var(--kind-agent) 8%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--kind-agent) 25%, transparent)' }}
      >
        <span className="mt-[3px] h-[7px] w-[7px] flex-none rounded-full" style={{ background: 'var(--kind-agent)' }} />
        <span className="text-[12px] leading-relaxed text-ink-2">{t('set.crossOrgNote')}</span>
      </div>
    </>
  );
}
