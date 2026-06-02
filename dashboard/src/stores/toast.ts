import { create } from 'zustand';

export interface Toast {
  id: string;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  show: (message: string) => void;
  dismiss: (id: string) => void;
}

// Track auto-dismiss timers so dismiss() can clear them (no leaked timers).
const timers = new Map<string, ReturnType<typeof setTimeout>>();

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  show: (message) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    set((s) => ({ toasts: [...s.toasts, { id, message }] }));
    const tid = setTimeout(() => {
      timers.delete(id);
      get().dismiss(id);
    }, 4000);
    timers.set(id, tid);
  },
  dismiss: (id) => {
    const tid = timers.get(id);
    if (tid) {
      clearTimeout(tid);
      timers.delete(id);
    }
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  },
}));
