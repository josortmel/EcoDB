import { useToastStore } from '../stores/toast';

export function Toasts() {
  const toasts = useToastStore((s) => s.toasts);

  return (
    <div className="fixed bottom-5 left-1/2 z-[70] flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="flex items-center gap-3 rounded-btn px-4 py-2.5"
          style={{ background: 'var(--card-bg)', boxShadow: 'var(--elev)', backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' }}
        >
          <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: 'var(--grn)', boxShadow: '0 0 6px rgba(78,158,106,0.5)' }} />
          <span className="text-[12.5px] text-ink-1">{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
