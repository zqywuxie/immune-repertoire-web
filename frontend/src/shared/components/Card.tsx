import type { ReactNode } from "react";

type CardProps = {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
  ariaLabel?: string;
};

export function Card({ children, onClick, className = "", ariaLabel }: CardProps) {
  return (
    <div
      className={`card ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      aria-label={ariaLabel}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-card)",
        padding: "var(--spacing-xl)",
        boxShadow: "var(--shadow-sm)",
        border: "1px solid var(--separator)",
        transition: `transform var(--duration-fast) ease-out, box-shadow var(--duration-fast) ease-out`,
        cursor: onClick ? "pointer" : "default",
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = "scale(1.01)";
          e.currentTarget.style.boxShadow = "var(--shadow-md)";
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "scale(1)";
        e.currentTarget.style.boxShadow = "var(--shadow-sm)";
      }}
    >
      {children}
    </div>
  );
}
