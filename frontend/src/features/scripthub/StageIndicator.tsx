import { Check } from "lucide-react";

export interface StageIndicatorStep {
  label: string;
  description?: string;
}

interface StageIndicatorProps {
  steps: StageIndicatorStep[];
  currentStep: number; // 0-indexed
  completedSteps: number[];
}

const DEFAULT_STEPS: StageIndicatorStep[] = [
  { label: "数据", description: "选择数据" },
  { label: "检查", description: "核对输入" },
  { label: "配置", description: "配置分析" },
  { label: "运行", description: "运行分析" },
  { label: "结果", description: "查看结果" },
];

export function StageIndicator({
  steps = DEFAULT_STEPS,
  currentStep,
  completedSteps,
}: StageIndicatorProps) {
  return (
    <div
      role="list"
      aria-label="分析步骤"
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        gap: 0,
        padding: "var(--spacing-xl) var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-card)",
        border: "1px solid var(--separator)",
        boxShadow: "var(--shadow-sm)",
        overflowX: "auto",
      }}
    >
      {steps.map((step, idx) => {
        const isActive = idx === currentStep;
        const isCompleted = completedSteps.includes(idx);
        const isPending = !isActive && !isCompleted;

        return (
          <div
            key={idx}
            style={{
              display: "flex",
              alignItems: "flex-start",
              flex: idx < steps.length - 1 ? 1 : undefined,
            }}
          >
            <div
              role="listitem"
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "var(--spacing-sm)",
                minWidth: "64px",
                flexShrink: 0,
              }}
            >
              {/* Step circle */}
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  fontSize: "0.85rem",
                  fontWeight: 700,
                  flexShrink: 0,
                  transition: "all var(--duration-normal) ease",
                  ...(isCompleted
                    ? {
                        background: "var(--success)",
                        color: "#fff",
                        border: "2px solid var(--success)",
                      }
                    : isActive
                      ? {
                          background: "var(--accent)",
                          color: "#fff",
                          border: "2px solid var(--accent)",
                          boxShadow: "0 0 0 3px rgba(0, 113, 227, 0.2)",
                        }
                      : {
                          background: "transparent",
                          color: "var(--text-tertiary)",
                          border: "2px solid var(--separator)",
                        }),
                }}
                aria-label={`步骤 ${idx + 1}: ${
                  isCompleted ? "complete" : isActive ? "current" : "pending"
                } — ${step.label}`}
              >
                {isCompleted ? <Check size={16} strokeWidth={3} /> : idx + 1}
              </div>

              {/* Label */}
              <div style={{ textAlign: "center" }}>
                <div
                  style={{
                    fontSize: "0.72rem",
                    fontWeight: isActive ? 600 : 400,
                    color: isActive
                      ? "var(--text-primary)"
                      : isCompleted
                        ? "var(--success)"
                        : "var(--text-tertiary)",
                    transition: "color var(--duration-fast)",
                    lineHeight: 1.3,
                    whiteSpace: "nowrap",
                  }}
                >
                  {step.label}
                </div>
                {step.description && (
                  <div
                    style={{
                      fontSize: "0.62rem",
                      color: "var(--text-tertiary)",
                      marginTop: "2px",
                      lineHeight: 1.2,
                    }}
                  >
                    {step.description}
                  </div>
                )}
              </div>
            </div>

            {/* Connector */}
            {idx < steps.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: "2px",
                  marginTop: "17px",
                  minWidth: "20px",
                  borderRadius: "1px",
                  background: isCompleted ? "var(--success)" : "var(--separator)",
                  transition: "background var(--duration-normal) ease-out",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
