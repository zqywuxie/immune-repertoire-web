import { Component, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

type Props = {
  children: ReactNode;
  fallback?: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          role="alert"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "var(--spacing-lg)",
            padding: "var(--spacing-4xl) var(--spacing-xl)",
            textAlign: "center",
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-card)",
            border: "1px solid var(--separator)",
          }}
        >
          <AlertTriangle size={40} strokeWidth={1} style={{ color: "var(--danger)" }} />
          <div>
            <h3 style={{ margin: 0, color: "var(--text-primary)" }}>
              Something went wrong
            </h3>
            <p
              style={{
                margin: "6px 0 0",
                color: "var(--text-secondary)",
                fontSize: "0.875rem",
                maxWidth: "480px",
              }}
            >
              {this.state.error?.message || "An unexpected error occurred."}
            </p>
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "10px 20px",
              borderRadius: "var(--radius-control)",
              background: "var(--accent)",
              color: "#ffffff",
              fontWeight: 500,
            }}
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
