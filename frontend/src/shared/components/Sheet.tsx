import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

type SheetProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  keepMounted?: boolean;
  layer?: number;
  panelClassName?: string;
};

export function Sheet({ open, onClose, title, children, keepMounted = false, layer = 100, panelClassName }: SheetProps) {
  const panel = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const getControls = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('*') || []).filter(node => node.tabIndex >= 0 && !node.matches(':disabled') && !node.closest('[hidden]') && (!node.closest('details:not([open])') || node.tagName === 'SUMMARY'));
    if (!panel.current?.contains(document.activeElement)) (getControls()[0] || panel.current)?.focus();
    const handleKey = (event: KeyboardEvent) => {
      const top = Array.from(document.querySelectorAll<HTMLElement>("[data-sheet-panel]"))
        .filter(node => !node.closest("[hidden]"))
        .sort((left, right) => Number(left.style.zIndex) - Number(right.style.zIndex)).at(-1);
      if (event.defaultPrevented || top !== panel.current) return;
      if (event.key === "Escape") { event.preventDefault(); closeRef.current(); }
      if (event.key === "Tab") {
        const controls = getControls(); const first = controls[0]; const last = controls[controls.length - 1];
        if (!first) { event.preventDefault(); panel.current?.focus(); }
        else if (event.shiftKey && (document.activeElement === first || !panel.current?.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !panel.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.removeEventListener("keydown", handleKey); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, [open]);
  if (!open && !keepMounted) return null;

  return (
    <div hidden={!open}>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.2)",
          zIndex: layer,
          backdropFilter: "blur(2px)",
        }}
      />
      <div
        ref={panel}
        data-sheet-panel
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: layer + 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          className={panelClassName}
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
              aria-label="关闭"
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
    </div>
  );
}
