import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel, PanelState } from './Panel';
import { useToastStore } from '../stores/toast';
import { asArray } from '../lib/asArray';
import {
  useStopEntities,
  useCreateStopEntity,
  useDeleteStopEntity,
  type StopEntity,
} from '../hooks/settings';

const ACCENT = 'var(--sec-settings)';

function Input({
  value,
  onChange,
  placeholder,
  wide,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  wide?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder={placeholder}
      className={`rounded-md px-3 py-2 font-mono text-[12px] text-ink-1 outline-none placeholder:text-ink-3 ${wide ? 'min-w-[140px] flex-1' : 'w-[130px]'}`}
      style={{
        background: 'var(--field-bg)',
        boxShadow: focused
          ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
          : 'inset 0 1px 3px var(--inset), inset 0 0 0 1px var(--card-hairline)',
      }}
    />
  );
}

function PrimaryBtn({ children, disabled }: { children: React.ReactNode; disabled?: boolean }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      className="rounded-btn bg-btn-primary px-4 py-2 font-body text-[12px] font-semibold text-white disabled:opacity-50"
      style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}
    >
      {children}
    </button>
  );
}

function RowBtn({
  children,
  onClick,
  danger,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-sm px-2.5 py-1 font-mono text-[11px] disabled:opacity-50 ${danger ? 'text-red' : 'text-ink-2'}`}
      style={
        danger
          ? { background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }
          : { background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }
      }
    >
      {children}
    </button>
  );
}

export function StopEntitiesPanel() {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const q = useStopEntities();
  const create = useCreateStopEntity();
  const del = useDeleteStopEntity();
  const [name, setName] = useState('');
  const [reason, setReason] = useState('');
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const onDelete = (id: number) => {
    if (confirmId !== id) {
      setConfirmId(id);
      return;
    }
    del.mutate(id, {
      onSuccess: () => setConfirmId(null),
      onError: () => {
        setConfirmId(null);
        toast(t('set.deleteFailed'));
      },
    });
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || create.isPending) return;
    create.mutate(
      { name: name.trim(), reason: reason.trim() || undefined },
      {
        onSuccess: () => {
          setName('');
          setReason('');
        },
      },
    );
  };

  return (
    <Panel title={t('set.stop.title')} accent={ACCENT} className="md:col-span-2 xl:col-span-3">
      <form onSubmit={onSubmit} className="mb-3 flex flex-wrap gap-2">
        <Input value={name} onChange={setName} placeholder={t('set.stop.name')} />
        <Input value={reason} onChange={setReason} placeholder={t('set.stop.reason')} wide />
        <PrimaryBtn disabled={create.isPending}>{t('set.stop.add')}</PrimaryBtn>
      </form>
      <PanelState
        loading={q.isPending}
        error={q.isError}
        onRetry={() => void q.refetch()}
        empty={asArray(q.data).length === 0}
        emptyLabel={t('set.stop.none')}
      >
        <div className="flex max-h-[240px] flex-col overflow-y-auto">
          {asArray<StopEntity>(q.data).map((en) => (
            <div key={en.id} className="flex items-center gap-3 border-b border-[var(--card-hairline)] py-2.5 last:border-0">
              <span className="flex-1 truncate font-mono text-[12.5px] text-ink-1">{en.name}</span>
              {en.reason && <span className="flex-none truncate font-mono text-[10.5px] text-ink-3">{en.reason}</span>}
              <RowBtn onClick={() => onDelete(en.id)} danger disabled={del.isPending}>
                {confirmId === en.id ? t('set.confirmDelete') : t('set.stop.delete')}
              </RowBtn>
            </div>
          ))}
        </div>
      </PanelState>
    </Panel>
  );
}
