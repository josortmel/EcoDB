// Shared status filter — tint-selected chips (no side-stripe, anti-slop). Used
// by Foresights + Skills tabs. The empty-string option means "All".
export function StatusChips({ value, options, onChange }: { value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const active = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={active}
            className={`rounded-[20px] px-2.5 py-1 font-mono text-[10.5px] transition-colors ${active ? 'text-ink-1' : 'text-ink-3 hover:text-ink-1'}`}
            style={
              active
                ? { background: 'color-mix(in srgb, var(--sec-memory-agent) 14%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)' }
                : { background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
