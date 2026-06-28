import type { ReactNode } from "react";
import { X } from "lucide-react";

type SheetProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
};

export function Sheet({ open, onClose, title, children }: SheetProps) {
  if (!open) return null;

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.2)",
          zIndex: 100,
          backdropFilter: "blur(2px)",
        }}
      />
      <div
        role="dialog"
        aria-label={title}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 101,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            pointerEvents: "auto",
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-card)",
            boxShadow: "var(--shadow-lg)",
            padding: "var(--spacing-2xl)",
            minWidth: "min(480px, 90vw)",
            maxWidth: "90vw",
            maxHeight: "85vh",
            overflow: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "var(--spacing-lg)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            {title && <h3 style={{ margin: 0 }}>{title}</h3>}
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                color: "var(--text-secondary)",
              }}
            >
              <X size={18} />
            </button>
          </div>
          {children}
        </div>
      </div>
    </>
  );
}
