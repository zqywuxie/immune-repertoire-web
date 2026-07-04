import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CheckCircle, AlertCircle, Info, X } from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────

export type ToastType = "success" | "error" | "info" | "warning";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toasts: Toast[];
  addToast: (message: string, type?: ToastType) => void;
  removeToast: (id: number) => void;
}

// ── Context ────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue | null>(null);

let _nextId = 1;

// ── Provider ───────────────────────────────────────────────────────────

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (message: string, type: ToastType = "info") => {
      const id = _nextId++;
      setToasts((prev) => [...prev.slice(-4), { id, message, type }]); // max 5 visible
      setTimeout(() => removeToast(id), 4000);
    },
    [removeToast]
  );

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer />
    </ToastContext.Provider>
  );
}

// ── Hook ───────────────────────────────────────────────────────────────

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

// ── Container ──────────────────────────────────────────────────────────

function ToastContainer() {
  const { toasts, removeToast } = useContext(ToastContext)!;

  if (!toasts.length) return null;

  return (
    <div
      aria-live="polite"
      style={{
        position: "fixed",
        bottom: "var(--spacing-2xl)",
        right: "var(--spacing-2xl)",
        zIndex: 200,
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-sm)",
        maxWidth: "420px",
        pointerEvents: "auto",
      }}
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

// ── Item ───────────────────────────────────────────────────────────────

const TOAST_STYLES: Record<ToastType, { bg: string; border: string; icon: typeof CheckCircle }> = {
  success: { bg: "#1a3a2a", border: "var(--success)", icon: CheckCircle },
  error: { bg: "#3a1a1a", border: "var(--danger)", icon: AlertCircle },
  warning: { bg: "#3a351a", border: "var(--warning)", icon: AlertCircle },
  info: { bg: "#1a2a3a", border: "var(--accent)", icon: Info },
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const style = TOAST_STYLES[toast.type];
  const Icon = style.icon;

  return (
    <div
      className="toast-enter"
      role="alert"
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--spacing-sm)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        borderRadius: "var(--radius-panel)",
        background: style.bg,
        border: `1px solid ${style.border}`,
        boxShadow: "var(--shadow-lg)",
        backdropFilter: "blur(8px)",
        animation: "toast-slide-in 0.3s ease-out",
        pointerEvents: "auto",
      }}
    >
      <Icon size={18} style={{ color: style.border, flexShrink: 0, marginTop: "1px" }} />
      <span style={{ flex: 1, fontSize: "0.85rem", color: "var(--text-primary)", lineHeight: 1.45 }}>
        {toast.message}
      </span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{
          flexShrink: 0,
          width: "24px",
          height: "24px",
          display: "grid",
          placeItems: "center",
          borderRadius: "50%",
          color: "var(--text-tertiary)",
          padding: 0,
          border: "none",
          background: "transparent",
          cursor: "pointer",
        }}
      >
        <X size={14} />
      </button>
    </div>
  );
}
