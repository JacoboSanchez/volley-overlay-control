import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

export type ToastType = 'success' | 'error';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastApi {
  toast: (message: string, type?: ToastType) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

const TOAST_MS = 2800;

/** Lightweight transient-notification layer for the account pages. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const toast = useCallback((message: string, type: ToastType = 'success') => {
    const id = ++idRef.current;
    setItems((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, TOAST_MS);
  }, []);

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      <div className="acc-toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`acc-toast ${t.type}`} role="status">
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/** Returns the toast function. No-op when rendered outside a provider (e.g.
 *  isolated component tests) so callers can use it unconditionally. */
export function useToast(): ToastApi {
  return useContext(ToastCtx) ?? { toast: () => {} };
}
