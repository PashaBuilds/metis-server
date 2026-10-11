import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import s from './Toast.module.css';

interface ToastItem {
  id: number;
  message: string;
  tone: 'ok' | 'error';
  undo?: () => Promise<void> | void;
  duration: number;
}

interface ToastApi {
  show: (message: string, opts?: { tone?: 'ok' | 'error'; undo?: () => Promise<void> | void; duration?: number }) => void;
}

const Ctx = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('ToastProvider eksik');
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);
  const show = useCallback<ToastApi['show']>((message, opts) => {
    const id = next.current++;
    // "Geri al" olan toast 8 sn kalır (brief 4).
    const duration = opts?.duration ?? (opts?.undo ? 8000 : 4500);
    setItems((all) => [...all.slice(-3), { id, message, tone: opts?.tone ?? 'ok', undo: opts?.undo, duration }]);
  }, []);
  return (
    <Ctx.Provider value={{ show }}>
      {children}
      <div className={s.region} role="region" aria-label="Bildirimler">
        <ol className={s.list} aria-live="polite">
          {items.map((t) => (
            <ToastView key={t.id} item={t} onDone={() => dismiss(t.id)} />
          ))}
        </ol>
      </div>
    </Ctx.Provider>
  );
}

function ToastView({ item, onDone }: { item: ToastItem; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(onDone, item.duration);
    return () => window.clearTimeout(timer);
  }, [item.duration, onDone]);
  const Icon = item.tone === 'ok' ? CheckCircle2 : AlertTriangle;
  return (
    <li className={s.item}>
      <div className={[s.toast, s[item.tone]].join(' ')} role={item.tone === 'error' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden className={s.icon} />
      <span className={s.msg}>{item.message}</span>
      {item.undo && (
        <button
          type="button"
          className={s.undo}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await item.undo?.();
            } finally {
              onDone();
            }
          }}
        >
          Geri al
        </button>
      )}
      <button type="button" className={s.close} onClick={onDone} aria-label="Bildirimi kapat">
        <X size={16} aria-hidden />
      </button>
      <span className={s.timer} style={{ animationDuration: `${item.duration}ms` }} aria-hidden />
      </div>
    </li>
  );
}
