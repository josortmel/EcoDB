import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { asArray } from '../../lib/asArray';
import { useAgents, type AgentSummary } from '../../hooks/useMemoryAgent';

// Shared agent picker for the Foresights/Skills tabs. The selection lives in
// MemoryAgentPage so it persists across both tabs. Auto-selects the first agent
// once the list loads and nothing is chosen yet.
export function AgentSelect({ agent, onAgentChange }: { agent?: string; onAgentChange: (agent: string) => void }) {
  const { t } = useTranslation();
  const q = useAgents();
  const agents = asArray<AgentSummary>(q.data?.items);
  const first = agents[0]?.identifier;
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!agent && first) onAgentChange(first);
    // Re-run only when the selection or the available first agent changes — not on
    // every parent render that hands a fresh onAgentChange identity (IC2).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, first]);

  return (
    <label className="flex items-center gap-2">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.agentSelect.label')}</span>
      <select
        value={agent ?? ''}
        onChange={(e) => onAgentChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="rounded-[7px] px-2.5 py-1.5 font-mono text-[11px] text-ink-1 outline-none"
        style={{ background: 'var(--inset)', boxShadow: focused ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)' : 'inset 0 0 0 1px var(--card-hairline)' }}
      >
        <option value="" disabled>
          {t('ma.agentSelect.placeholder')}
        </option>
        {agents.map((a) => (
          <option key={a.id} value={a.identifier}>
            {a.display_name ?? a.identifier}
          </option>
        ))}
      </select>
    </label>
  );
}
