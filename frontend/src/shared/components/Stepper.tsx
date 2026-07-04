import { Check } from "lucide-react";
import styles from "./Stepper.module.css";

/* ── Types ── */

export interface StepDef {
  label: string;
  description?: string;
}

export interface StepperProps {
  steps: StepDef[];
  /** 0-based index of the current step. */
  currentStep: number;
  /** Render vertically instead of horizontally. */
  vertical?: boolean;
}

export type StepStatus = "complete" | "current" | "pending";

function getStatus(index: number, currentStep: number): StepStatus {
  if (index < currentStep) return "complete";
  if (index === currentStep) return "current";
  return "pending";
}

/* ── Component ── */

export function Stepper({ steps, currentStep, vertical = false }: StepperProps) {
  if (vertical) {
    return (
      <div className={styles.vertical} role="list" aria-label="Progress steps">
        {steps.map((step, idx) => {
          const status = getStatus(idx, currentStep);
          return (
            <div key={idx} className={styles.verticalStep} role="listitem">
              <div className={styles.verticalNode}>
                <StepCircle status={status} index={idx} />
                {idx < steps.length - 1 && (
                  <div
                    className={`${styles.verticalConnector} ${
                      status === "complete"
                        ? styles.connectorComplete
                        : styles.connectorIncomplete
                    }`}
                  />
                )}
              </div>
              <div className={styles.verticalContent}>
                <span
                  className={`${styles.verticalLabel} ${
                    status === "complete"
                      ? styles.stepLabelComplete
                      : status === "current"
                        ? styles.stepLabelCurrent
                        : styles.stepLabelPending
                  }`}
                >
                  {step.label}
                </span>
                {step.description && (
                  <span className={styles.verticalDescription}>
                    {step.description}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className={styles.stepper} role="list" aria-label="Progress steps">
      {steps.map((step, idx) => {
        const status = getStatus(idx, currentStep);
        return (
          <div key={idx} className={styles.step} role="listitem">
            <div className={styles.stepNode}>
              <StepCircle status={status} index={idx} />
              <span
                className={`${styles.stepLabel} ${
                  status === "complete"
                    ? styles.stepLabelComplete
                    : status === "current"
                      ? styles.stepLabelCurrent
                      : styles.stepLabelPending
                }`}
              >
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={`${styles.stepConnector} ${
                  status === "complete"
                    ? styles.connectorComplete
                    : styles.connectorIncomplete
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Internal ── */

function StepCircle({
  status,
  index,
}: {
  status: StepStatus;
  index: number;
}) {
  const cls =
    status === "complete"
      ? styles.stepComplete
      : status === "current"
        ? styles.stepCurrent
        : styles.stepPending;

  return (
    <div
      className={`${styles.stepCircle} ${cls}`}
      aria-label={`Step ${index + 1}: ${status}`}
    >
      {status === "complete" ? (
        <Check size={14} strokeWidth={3} />
      ) : (
        index + 1
      )}
    </div>
  );
}
