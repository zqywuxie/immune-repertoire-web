type Props = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  size?: "sm" | "md";
};

const SIZES = {
  sm: { w: 36, h: 20, dot: 14, pad: 3 },
  md: { w: 48, h: 26, dot: 20, pad: 3 },
};

export function Toggle({ checked, onChange, disabled, label, size = "md" }: Props) {
  const s = SIZES[size];

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--spacing-sm)",
        background: "none",
        border: "none",
        padding: 0,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        fontFamily: "var(--font-family)",
      }}
    >
      {/* Track */}
      <span
        style={{
          display: "inline-block",
          width: `${s.w}px`,
          height: `${s.h}px`,
          borderRadius: `${s.h}px`,
          background: checked ? "var(--accent)" : "var(--separator)",
          transition: "background var(--duration-fast)",
          position: "relative",
          flexShrink: 0,
        }}
      >
        {/* Knob */}
        <span
          style={{
            position: "absolute",
            top: `${s.pad}px`,
            left: checked ? `${s.w - s.dot - s.pad}px` : `${s.pad}px`,
            width: `${s.dot}px`,
            height: `${s.dot}px`,
            borderRadius: "50%",
            background: "#fff",
            boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
            transition: "left var(--duration-fast) cubic-bezier(0.2, 0.85, 0.32, 1.2)",
          }}
        />
      </span>
      {label && (
        <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", userSelect: "none" }}>
          {label}
        </span>
      )}
    </button>
  );
}
