import { useState, useRef, useEffect, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

interface SelectOption<T = string> {
  value: T;
  label: ReactNode;
}

type Props<T = string> = {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
};

export function Select<T extends string = string>({
  value,
  options,
  onChange,
  placeholder = "Select…",
  disabled,
  className,
  style,
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className={className} style={{ position: "relative", ...style }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--spacing-sm)",
          width: "100%",
          minHeight: "42px",
          padding: "8px 12px",
          borderRadius: "var(--radius-control)",
          border: open ? "1px solid var(--accent)" : "1px solid var(--separator)",
          background: disabled ? "var(--bg-inset)" : "var(--bg-elevated)",
          color: selected ? "var(--text-primary)" : "var(--text-tertiary)",
          fontSize: "0.85rem",
          cursor: disabled ? "not-allowed" : "pointer",
          transition: "border-color var(--duration-fast), box-shadow var(--duration-fast)",
          boxShadow: open ? "0 0 0 3px rgba(0,113,227,0.15)" : "none",
          fontFamily: "var(--font-family)",
        }}
      >
        <span style={{ flex: 1, textAlign: "left" }}>{selected ? selected.label : placeholder}</span>
        <ChevronDown
          size={14}
          style={{
            color: "var(--text-tertiary)",
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform var(--duration-fast)",
            flexShrink: 0,
          }}
        />
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: "6px",
            borderRadius: "var(--radius-control)",
            background: "var(--bg-elevated)",
            border: "1px solid var(--separator)",
            boxShadow: "var(--shadow-lg)",
            zIndex: 50,
            maxHeight: "240px",
            overflow: "auto",
            animation: "fade-in 0.15s ease-out",
          }}
        >
          {options.map((opt) => (
            <button
              key={String(opt.value)}
              type="button"
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "10px 14px",
                border: "none",
                background: opt.value === value ? "rgba(0,113,227,0.08)" : "transparent",
                color: opt.value === value ? "var(--accent)" : "var(--text-primary)",
                fontSize: "0.85rem",
                fontWeight: opt.value === value ? 500 : 400,
                cursor: "pointer",
                fontFamily: "var(--font-family)",
                transition: "background var(--duration-fast)",
              }}
              onMouseEnter={(e) => {
                if (opt.value !== value) (e.target as HTMLButtonElement).style.background = "var(--bg-inset)";
              }}
              onMouseLeave={(e) => {
                if (opt.value !== value) (e.target as HTMLButtonElement).style.background = "transparent";
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
