import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Field, SelectInput, TextInput } from './ModalShell';

type Freq = 'manual' | 'daily' | 'weekly' | 'monthly' | 'advanced';

interface CronState {
  freq: Freq;
  hour: number;
  weekday: number;
  dom: number;
  raw: string;
}

const pad = (n: number) => String(n).padStart(2, '0');

// Parse a cron string into the builder's structured state. Only the shapes the
// builder produces round-trip cleanly; anything else falls back to advanced/raw.
function parse(cron: string | null): CronState {
  const base: CronState = { freq: 'manual', hour: 3, weekday: 0, dom: 1, raw: '' };
  if (!cron) return base;
  const daily = cron.match(/^0 (\d{1,2}) \* \* \*$/);
  if (daily) return { ...base, freq: 'daily', hour: Number(daily[1]) };
  const weekly = cron.match(/^0 (\d{1,2}) \* \* ([0-6])$/);
  if (weekly) return { ...base, freq: 'weekly', hour: Number(weekly[1]), weekday: Number(weekly[2]) };
  const monthly = cron.match(/^0 (\d{1,2}) (\d{1,2}) \* \*$/);
  if (monthly) return { ...base, freq: 'monthly', hour: Number(monthly[1]), dom: Number(monthly[2]) };
  return { ...base, freq: 'advanced', raw: cron };
}

function build(s: CronState): string | null {
  switch (s.freq) {
    case 'manual':
      return null;
    case 'daily':
      return `0 ${s.hour} * * *`;
    case 'weekly':
      return `0 ${s.hour} * * ${s.weekday}`;
    case 'monthly':
      return `0 ${s.hour} ${s.dom} * *`;
    case 'advanced': {
      const raw = s.raw.trim();
      // Frontend guard: only emit cron-shaped input, else null (back to manual).
      // Defence in depth — the backend must still validate (adv-seg VS_CF2).
      return /^[\d\s*/,\-#]+$/.test(raw) ? raw : null;
    }
  }
}

const FREQS: Freq[] = ['manual', 'daily', 'weekly', 'monthly', 'advanced'];

// Human-readable schedule label for config rows (never raw cron, unless advanced).
export function cronLabel(cron: string | null, t: TFunction): string {
  const tx = t as (k: string) => string; // dynamic weekday keys (typed-t can't infer)
  const s = parse(cron);
  const time = `${pad(s.hour)}:00`;
  switch (s.freq) {
    case 'manual':
      return t('ma.configs.cron.manual');
    case 'daily':
      return `${t('ma.configs.cron.daily')} · ${time}`;
    case 'weekly':
      return `${tx(`ma.configs.cron.weekday.${s.weekday}`)} · ${time}`;
    case 'monthly':
      return `${t('ma.configs.cron.monthly')} · ${s.dom} · ${time}`;
    case 'advanced':
      return s.raw || cron || '—';
  }
}

// Schedule builder — the user picks day/time, never types raw cron (Pepe's "pon
// las horas"). Emits the cron string upward; an advanced escape hatch remains for
// power users. value is the current cron (null = manual only).
export function CronBuilder({ value, onChange }: { value: string | null; onChange: (cron: string | null) => void }) {
  const { t } = useTranslation();
  const tx = t as (k: string) => string; // dynamic weekday keys (typed-t can't infer)
  const [s, setS] = useState<CronState>(() => parse(value));

  // Emit whenever the structured state changes. onChange intentionally omitted
  // from deps — it's a setter from the parent and would retrigger on every render.
  useEffect(() => {
    onChange(build(s));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s]);

  const set = (patch: Partial<CronState>) => setS((prev) => ({ ...prev, ...patch }));

  return (
    <div className="flex flex-col gap-3">
      <Field label={t('ma.configs.cron.frequency')}>
        <SelectInput value={s.freq} onChange={(v) => set({ freq: v as Freq })}>
          {FREQS.map((f) => (
            <option key={f} value={f}>
              {t(`ma.configs.cron.${f}`)}
            </option>
          ))}
        </SelectInput>
      </Field>

      {s.freq === 'weekly' && (
        <Field label={t('ma.configs.cron.day')}>
          <SelectInput value={String(s.weekday)} onChange={(v) => set({ weekday: Number(v) })}>
            {[0, 1, 2, 3, 4, 5, 6].map((w) => (
              <option key={w} value={w}>
                {tx(`ma.configs.cron.weekday.${w}`)}
              </option>
            ))}
          </SelectInput>
        </Field>
      )}

      {s.freq === 'monthly' && (
        <Field label={t('ma.configs.cron.dayOfMonth')}>
          <SelectInput value={String(s.dom)} onChange={(v) => set({ dom: Number(v) })}>
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </SelectInput>
        </Field>
      )}

      {(s.freq === 'daily' || s.freq === 'weekly' || s.freq === 'monthly') && (
        <Field label={t('ma.configs.cron.time')}>
          <SelectInput value={String(s.hour)} onChange={(v) => set({ hour: Number(v) })}>
            {Array.from({ length: 24 }, (_, i) => i).map((h) => (
              <option key={h} value={h}>
                {pad(h)}:00
              </option>
            ))}
          </SelectInput>
        </Field>
      )}

      {s.freq === 'advanced' && (
        <Field label={t('ma.configs.cron.cronRaw')}>
          <TextInput value={s.raw} onChange={(v) => set({ raw: v })} placeholder="0 3 * * 0" maxLength={120} />
        </Field>
      )}
    </div>
  );
}
