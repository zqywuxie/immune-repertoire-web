# Frontend Modular Redesign — Apple-style Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monolithic Migration Console (`App.tsx`) with a 3-page routed SPA (Dashboard / Database / ScriptHub), Apple-inspired design system.

**Architecture:** React Router v7 with `BrowserRouter`, outlet-based shell layout (Rail sidebar + page content), feature modules for projects/assets/jobs, shared component library, CSS custom properties design tokens. Existing `shared/api/` and `shared/types/` reused without changes.

**Tech Stack:** Vite 6, React 19, TypeScript 5.7, react-router-dom v7, lucide-react 0.468

---

### Task 1: Install react-router-dom

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install react-router-dom**

```bash
cd frontend && npm install react-router-dom@7
```

- [ ] **Step 2: Verify install**

```bash
cd frontend && npm ls react-router-dom
```

Expected: `react-router-dom@7.x.x`

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add react-router-dom v7 for SPA routing"
```

---

### Task 2: Create design tokens and global styles

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/global.css`

- [ ] **Step 1: Write tokens.css**

```css
:root {
  /* ── Backgrounds ── */
  --bg-root: #f5f5f7;
  --bg-elevated: #ffffff;
  --bg-inset: #e8e8ed;

  /* ── Text ── */
  --text-primary: #1d1d1f;
  --text-secondary: #6e6e73;
  --text-tertiary: #aeaeb2;

  /* ── Accent colors ── */
  --accent: #0071e3;
  --accent-hover: #0077ed;
  --success: #34c759;
  --warning: #ff9500;
  --danger: #ff3b30;

  /* ── Separators & shadows ── */
  --separator: rgba(60, 60, 67, 0.12);
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 8px 30px rgba(0, 0, 0, 0.08);

  /* ── Radius ── */
  --radius-card: 20px;
  --radius-panel: 16px;
  --radius-control: 12px;
  --radius-pill: 20px;

  /* ── Layout ── */
  --rail-width: 72px;
  --content-max: 1200px;
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 12px;
  --spacing-lg: 16px;
  --spacing-xl: 20px;
  --spacing-2xl: 24px;
  --spacing-3xl: 32px;
  --spacing-4xl: 40px;
  --spacing-5xl: 48px;

  /* ── Typography ── */
  --font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
    "PingFang SC", "Microsoft YaHei", sans-serif;

  /* ── Transitions ── */
  --duration-fast: 120ms;
  --duration-normal: 200ms;
  --duration-slow: 350ms;
}
```

- [ ] **Step 2: Write global.css**

```css
@import "./tokens.css";

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  font-family: var(--font-family);
  font-size: 15px;
  font-weight: 400;
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--bg-root);
  min-height: 100vh;
}

h1, h2, h3, h4 {
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

h1 { font-size: 2rem; }
h2 { font-size: 1.5rem; }
h3 { font-size: 1.125rem; }
h4 { font-size: 1rem; }

button {
  font-family: inherit;
  font-size: inherit;
  cursor: pointer;
  border: none;
  background: none;
}

a {
  color: var(--accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

input, select, textarea {
  font-family: inherit;
  font-size: inherit;
}

table {
  font-family: inherit;
  font-size: inherit;
}

/* ── Utility classes ── */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/
git commit -m "feat: add Apple-style design tokens and global reset"
```

---

### Task 3: Create useApi and usePolling hooks

**Files:**
- Create: `frontend/src/shared/hooks/useApi.ts`
- Create: `frontend/src/shared/hooks/usePolling.ts`

- [ ] **Step 1: Write useApi.ts**

```typescript
import { useCallback, useEffect, useReducer, useRef } from "react";

type State<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: string };

type Action<T> =
  | { type: "start" }
  | { type: "done"; data: T }
  | { type: "fail"; error: string };

function reducer<T>(_state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case "start":
      return { status: "loading" };
    case "done":
      return { status: "ready", data: action.data };
    case "fail":
      return { status: "error", error: action.error };
  }
}

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
) {
  const [state, dispatch] = useReducer(reducer<T>, { status: "idle" });
  const cancelled = useRef(false);

  const execute = useCallback(() => {
    dispatch({ type: "start" });
    fetcher()
      .then((data) => {
        if (!cancelled.current) dispatch({ type: "done", data });
      })
      .catch((err: unknown) => {
        if (!cancelled.current) {
          dispatch({
            type: "fail",
            error: err instanceof Error ? err.message : "Unknown error",
          });
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    cancelled.current = false;
    execute();
    return () => {
      cancelled.current = true;
    };
  }, [execute]);

  return { ...state, refetch: execute };
}
```

- [ ] **Step 2: Write usePolling.ts**

```typescript
import { useEffect, useRef, useState, useCallback } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 3000
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted = useRef(true);

  const poll = useCallback(() => {
    fetcher()
      .then((result) => {
        if (mounted.current) {
          setData(result);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : "Polling failed");
          setLoading(false);
        }
      });
  }, [fetcher]);

  useEffect(() => {
    mounted.current = true;
    poll();
    timer.current = setInterval(poll, intervalMs);
    return () => {
      mounted.current = false;
      if (timer.current) clearInterval(timer.current);
    };
  }, [poll, intervalMs]);

  return { data, error, loading };
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/hooks/
git commit -m "feat: add useApi and usePolling hooks"
```

---

### Task 4: Create base shared components (Card, Skeleton, StatusBadge, ProgressBar)

**Files:**
- Create: `frontend/src/shared/components/Card.tsx`
- Create: `frontend/src/shared/components/Skeleton.tsx`
- Create: `frontend/src/shared/components/StatusBadge.tsx`
- Create: `frontend/src/shared/components/ProgressBar.tsx`

- [ ] **Step 1: Write Card.tsx**

```typescript
import type { ReactNode, MouseEventHandler } from "react";

type CardProps = {
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLDivElement>;
  className?: string;
};

export function Card({ children, onClick, className = "" }: CardProps) {
  return (
    <div
      className={`card ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick(e as unknown as React.MouseEvent<HTMLDivElement>);
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
```

- [ ] **Step 2: Write Skeleton.tsx**

```typescript
type SkeletonProps = {
  width?: string;
  height?: string;
  variant?: "text" | "rect" | "circle";
  className?: string;
};

export function Skeleton({
  width,
  height,
  variant = "rect",
  className = "",
}: SkeletonProps) {
  const baseStyle: React.CSSProperties = {
    background: "var(--bg-inset)",
    animation: "breathe 1.8s ease-in-out infinite",
    width: width || "100%",
  };

  if (variant === "circle") {
    baseStyle.borderRadius = "50%";
    baseStyle.height = height || width || "40px";
  } else if (variant === "text") {
    baseStyle.borderRadius = "6px";
    baseStyle.height = height || "14px";
  } else {
    baseStyle.borderRadius = "var(--radius-panel)";
    baseStyle.height = height || "64px";
  }

  return <div className={className} style={baseStyle} aria-hidden="true" />;
}

export function SkeletonRow({ columns }: { columns: number }) {
  return (
    <tr>
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} style={{ padding: "12px 10px" }}>
          <Skeleton variant="text" width={`${60 + Math.random() * 30}%`} />
        </td>
      ))}
    </tr>
  );
}
```

- [ ] **Step 3: Write StatusBadge.tsx**

```typescript
const STATUS_COLORS: Record<string, string> = {
  queued: "#0071e3",
  running: "#ff9500",
  completed: "#34c759",
  failed: "#ff3b30",
  cancelled: "#aeaeb2",
};

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || "#aeaeb2";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "4px 10px",
        borderRadius: "var(--radius-pill)",
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "capitalize",
        background: `${color}18`,
        color: color,
        border: `1px solid ${color}30`,
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
        }}
      />
      {status}
    </span>
  );
}
```

- [ ] **Step 4: Write ProgressBar.tsx**

```typescript
export function ProgressBar({
  value,
  max = 100,
}: {
  value: number;
  max?: number;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      style={{
        width: "100%",
        height: "6px",
        borderRadius: "3px",
        background: "var(--bg-inset)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          borderRadius: "3px",
          background:
            pct >= 100 ? "var(--success)" : "var(--accent)",
          transition: "width 400ms ease-out",
        }}
      />
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/components/Card.tsx frontend/src/shared/components/Skeleton.tsx frontend/src/shared/components/StatusBadge.tsx frontend/src/shared/components/ProgressBar.tsx
git commit -m "feat: add Card, Skeleton, StatusBadge, ProgressBar components"
```

---

### Task 5: Create layout components (Rail, Tabs, Pagination, PageHeader, EmptyState, MetricCard, Sheet)

**Files:**
- Create: `frontend/src/shared/components/Rail.tsx`
- Create: `frontend/src/shared/components/Tabs.tsx`
- Create: `frontend/src/shared/components/Pagination.tsx`
- Create: `frontend/src/shared/components/PageHeader.tsx`
- Create: `frontend/src/shared/components/EmptyState.tsx`
- Create: `frontend/src/shared/components/MetricCard.tsx`
- Create: `frontend/src/shared/components/Sheet.tsx`

- [ ] **Step 1: Write Rail.tsx**

```typescript
import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

type RailLink = {
  to: string;
  icon: LucideIcon;
  label: string;
};

export function Rail({ links }: { links: RailLink[] }) {
  return (
    <nav
      style={{
        width: "var(--rail-width)",
        minHeight: "100vh",
        background: "#1d1d1f",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "var(--spacing-xl) 0",
        gap: "var(--spacing-md)",
        flexShrink: 0,
      }}
      aria-label="Main navigation"
    >
      <div
        style={{
          width: "40px",
          height: "40px",
          display: "grid",
          placeItems: "center",
          color: "var(--accent)",
          fontWeight: 800,
          fontSize: "1.1rem",
          letterSpacing: "0.04em",
          marginBottom: "var(--spacing-sm)",
        }}
      >
        IR
      </div>

      <div
        style={{
          width: "36px",
          height: "1px",
          background: "rgba(255,255,255,0.12)",
          marginBottom: "var(--spacing-sm)",
        }}
      />

      {links.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          aria-label={label}
          style={({ isActive }) => ({
            width: "44px",
            height: "44px",
            display: "grid",
            placeItems: "center",
            borderRadius: "var(--radius-control)",
            color: isActive ? "#ffffff" : "#aeaeb2",
            background: isActive ? "var(--accent)" : "transparent",
            transition: `background var(--duration-fast), color var(--duration-fast)`,
          })}
        >
          <Icon size={20} />
        </NavLink>
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: Write Tabs.tsx**

```typescript
type Tab = { key: string; label: string };

export function Tabs({
  tabs,
  activeKey,
  onChange,
}: {
  tabs: Tab[];
  activeKey: string;
  onChange: (key: string) => void;
}) {
  return (
    <div
      role="tablist"
      style={{
        display: "flex",
        gap: "var(--spacing-sm)",
        borderBottom: "1px solid var(--separator)",
        paddingBottom: "var(--spacing-md)",
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.key === activeKey;
        return (
          <button
            key={tab.key}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            style={{
              padding: "8px 16px",
              borderRadius: "var(--radius-pill)",
              fontWeight: 500,
              fontSize: "0.875rem",
              color: isActive ? "#ffffff" : "var(--text-secondary)",
              background: isActive ? "var(--accent)" : "transparent",
              border: isActive ? "none" : "1px solid var(--separator)",
              transition: `all var(--duration-fast)`,
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Write Pagination.tsx**

```typescript
export type PaginationInfo = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export function Pagination({
  pagination,
  onPageChange,
}: {
  pagination?: PaginationInfo;
  onPageChange: (page: number) => void;
}) {
  if (!pagination) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: "0.875rem" }}>No pagination data</p>;
  }

  const { page, total, total_pages } = pagination;
  const pages = Array.from({ length: Math.max(total_pages, 1) }, (_, i) => i + 1);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--spacing-md)",
        color: "var(--text-secondary)",
        fontSize: "0.875rem",
      }}
    >
      <span>
        {total} item{total !== 1 ? "s" : ""} · page {page} of{" "}
        {Math.max(total_pages, 1)}
      </span>
      <div style={{ display: "flex", gap: "var(--spacing-xs)" }}>
        <PageBtn disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          ←
        </PageBtn>
        {pages.map((p) => (
          <PageBtn
            key={p}
            active={p === page}
            onClick={() => onPageChange(p)}
          >
            {p}
          </PageBtn>
        ))}
        <PageBtn
          disabled={page >= total_pages}
          onClick={() => onPageChange(page + 1)}
        >
          →
        </PageBtn>
      </div>
    </div>
  );
}

function PageBtn({
  children,
  disabled,
  active,
  onClick,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      style={{
        minWidth: "36px",
        height: "36px",
        display: "grid",
        placeItems: "center",
        borderRadius: "var(--radius-control)",
        border: active ? "1px solid var(--accent)" : "1px solid var(--separator)",
        background: active ? "var(--accent)" : "var(--bg-elevated)",
        color: active ? "#ffffff" : disabled ? "var(--text-tertiary)" : "var(--text-primary)",
        fontWeight: active ? 600 : 400,
        fontSize: "0.875rem",
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.4 : 1,
      }}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Write PageHeader.tsx**

```typescript
import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  children?: ReactNode;
};

export function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--spacing-lg)",
      }}
    >
      <div>
        <h2 style={{ margin: 0 }}>{title}</h2>
        {subtitle && (
          <p
            style={{
              margin: "4px 0 0",
              color: "var(--text-secondary)",
              fontSize: "0.875rem",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </header>
  );
}
```

- [ ] **Step 5: Write EmptyState.tsx**

```typescript
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; to: string };
};

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-5xl) var(--spacing-xl)",
        textAlign: "center",
      }}
    >
      <Icon
        size={48}
        strokeWidth={1}
        style={{ color: "var(--text-tertiary)" }}
      />
      <div>
        <h3 style={{ margin: 0 }}>{title}</h3>
        {description && (
          <p
            style={{
              margin: "6px 0 0",
              color: "var(--text-secondary)",
              fontSize: "0.875rem",
            }}
          >
            {description}
          </p>
        )}
      </div>
      {action && (
        <button
          onClick={() => navigate(action.to)}
          style={{
            padding: "10px 20px",
            borderRadius: "var(--radius-control)",
            background: "var(--accent)",
            color: "#ffffff",
            fontWeight: 500,
            transition: `background var(--duration-fast)`,
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Write MetricCard.tsx**

```typescript
import type { LucideIcon } from "lucide-react";

type MetricCardProps = {
  icon: LucideIcon;
  label: string;
  value: number;
  color?: string;
};

export function MetricCard({
  icon: Icon,
  label,
  value,
  color = "var(--accent)",
}: MetricCardProps) {
  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-card)",
        padding: "var(--spacing-xl)",
        boxShadow: "var(--shadow-sm)",
        border: "1px solid var(--separator)",
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--spacing-lg)",
      }}
    >
      <div
        style={{
          width: "44px",
          height: "44px",
          borderRadius: "var(--radius-control)",
          background: `${color}12`,
          color: color,
          display: "grid",
          placeItems: "center",
          flexShrink: 0,
        }}
      >
        <Icon size={22} />
      </div>
      <div>
        <div
          style={{
            fontSize: "2rem",
            fontWeight: 700,
            lineHeight: 1,
            color: "var(--text-primary)",
          }}
        >
          {value.toLocaleString()}
        </div>
        <div
          style={{
            color: "var(--text-secondary)",
            fontSize: "0.875rem",
            marginTop: "4px",
          }}
        >
          {label}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Write Sheet.tsx** (minimal modal for future preview use)

```typescript
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
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/shared/components/
git commit -m "feat: add layout components (Rail, Tabs, Pagination, PageHeader, EmptyState, MetricCard, Sheet)"
```

---

### Task 6: Set up App shell with Router + Rail

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.css`

- [ ] **Step 1: Rewrite main.tsx with BrowserRouter**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./app/App";
import "./styles/global.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 2: Rewrite App.tsx as shell with Rail + Outlet**

```typescript
import { Routes, Route, Outlet } from "react-router-dom";
import { Database, FlaskConical, LayoutDashboard } from "lucide-react";
import { Rail } from "../shared/components/Rail";
import { Dashboard } from "./Dashboard";
import { DatabasePage } from "./Database";
import { ScriptHub } from "./ScriptHub";
import "./App.css";

const NAV_LINKS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/database", icon: Database, label: "Database" },
  { to: "/scripthub", icon: FlaskConical, label: "Script Hub" },
];

export function App() {
  return (
    <Routes>
      <Route
        element={
          <div className="shell">
            <Rail links={NAV_LINKS} />
            <main className="page-wrap">
              <Outlet />
            </main>
          </div>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="database" element={<DatabasePage />} />
        <Route path="database/:projectId" element={<DatabasePage />} />
        <Route path="scripthub" element={<ScriptHub />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 3: Replace App.css with shell-only styles**

```css
.shell {
  display: flex;
  min-height: 100vh;
}

.page-wrap {
  flex: 1;
  min-width: 0;
  padding: var(--spacing-3xl);
  max-width: var(--content-max);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2xl);
}

@media (max-width: 768px) {
  .shell {
    flex-direction: column;
  }

  .page-wrap {
    padding: var(--spacing-lg);
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.tsx frontend/src/app/App.tsx frontend/src/app/App.css
git commit -m "feat: set up App shell with BrowserRouter and Rail navigation"
```

---

### Task 7: Extract project feature components (ProjectCard, ProjectList)

**Files:**
- Create: `frontend/src/features/projects/ProjectCard.tsx`
- Create: `frontend/src/features/projects/ProjectList.tsx`

- [ ] **Step 1: Write ProjectCard.tsx**

```typescript
import { useNavigate } from "react-router-dom";
import { Card } from "../../shared/components/Card";
import type { ProjectSummary } from "../../shared/types/domain";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  const navigate = useNavigate();
  const assetCount = Object.values(project.asset_counts || {}).reduce(
    (s, c) => s + c,
    0
  );

  return (
    <Card onClick={() => navigate(`/database/${project.id}`)}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--spacing-md)",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h4
            style={{
              margin: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {project.name}
          </h4>
          {project.institution && (
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "0.8rem",
                margin: "4px 0 0",
              }}
            >
              {project.institution}
            </p>
          )}
        </div>
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 500,
            textTransform: "capitalize",
            padding: "3px 10px",
            borderRadius: "var(--radius-pill)",
            background:
              project.status === "active"
                ? "rgba(52,199,89,0.12)"
                : "var(--bg-inset)",
            color:
              project.status === "active"
                ? "var(--success)"
                : "var(--text-secondary)",
          }}
        >
          {project.status}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          gap: "var(--spacing-xl)",
          marginTop: "var(--spacing-lg)",
          fontSize: "0.875rem",
          color: "var(--text-secondary)",
        }}
      >
        <div>
          <strong style={{ color: "var(--text-primary)" }}>{assetCount}</strong>{" "}
          assets
        </div>
        <div>
          <strong style={{ color: "var(--text-primary)" }}>
            {project.sample_count || 0}
          </strong>{" "}
          samples
        </div>
        <div>
          <strong style={{ color: "var(--text-primary)" }}>
            {project.result_count || 0}
          </strong>{" "}
          results
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Write ProjectList.tsx**

```typescript
import { useApi } from "../../shared/hooks/useApi";
import { listProjects } from "../../shared/api/projects";
import { Skeleton } from "../../shared/components/Skeleton";
import { ProjectCard } from "./ProjectCard";

export function ProjectList() {
  const state = useApi(() => listProjects(), []);

  if (state.status === "loading") {
    return (
      <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height="100px" />
        ))}
      </div>
    );
  }

  if (state.status === "error") {
    return <p style={{ color: "var(--danger)" }}>{state.error}</p>;
  }

  const projects = state.status === "ready" ? state.data.projects : [];

  if (projects.length === 0) {
    return (
      <p style={{ color: "var(--text-tertiary)", textAlign: "center", padding: "var(--spacing-3xl)" }}>
        No projects found.
      </p>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
        gap: "var(--spacing-lg)",
      }}
    >
      {projects.map((p) => (
        <ProjectCard key={p.id} project={p} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/projects/
git commit -m "feat: add ProjectCard and ProjectList components"
```

---

### Task 8: Extract asset feature components (AssetTable, AssetUpload)

**Files:**
- Create: `frontend/src/features/assets/AssetTable.tsx`
- Create: `frontend/src/features/assets/AssetUpload.tsx`

- [ ] **Step 1: Write AssetTable.tsx**

```typescript
import { assetDownloadUrl, assetPreviewUrl } from "../../shared/api/projects";
import type { ProjectAsset } from "../../shared/types/domain";
import { SkeletonRow } from "../../shared/components/Skeleton";

function formatSize(size: number): string {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

export function AssetTable({
  assets,
  loading,
  emptyLabel = "No assets found.",
}: {
  assets: ProjectAsset[];
  loading: boolean;
  emptyLabel?: string;
}) {
  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        overflow: "hidden",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr
            style={{
              background: "var(--bg-root)",
              borderBottom: "1px solid var(--separator)",
            }}
          >
            {["Name", "Type", "Size", "Uploaded", "Actions"].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  padding: "12px 16px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--text-secondary)",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRow columns={5} />
          ) : assets.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                style={{
                  padding: "var(--spacing-3xl) var(--spacing-lg)",
                  textAlign: "center",
                  color: "var(--text-tertiary)",
                }}
              >
                {emptyLabel}
              </td>
            </tr>
          ) : (
            assets.map((asset) => (
              <tr
                key={asset.id}
                style={{ borderBottom: "1px solid var(--separator)" }}
              >
                <td
                  style={{
                    padding: "12px 16px",
                    maxWidth: "240px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {asset.original_name}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <span
                    style={{
                      padding: "2px 8px",
                      borderRadius: "var(--radius-pill)",
                      background: "var(--bg-inset)",
                      fontSize: "0.75rem",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {asset.asset_type}
                  </span>
                </td>
                <td style={{ padding: "12px 16px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  {formatSize(asset.size)}
                </td>
                <td style={{ padding: "12px 16px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  {formatDate(asset.uploaded_at)}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{ display: "flex", gap: "var(--spacing-xs)" }}>
                    <AssetLink href={assetPreviewUrl(asset.id)} label="Preview" />
                    <AssetLink href={assetDownloadUrl(asset.id)} label="Download" />
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function AssetLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      style={{
        padding: "6px 12px",
        borderRadius: "var(--radius-control)",
        border: "1px solid var(--separator)",
        color: "var(--accent)",
        fontSize: "0.8rem",
        fontWeight: 500,
        textDecoration: "none",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </a>
  );
}
```

- [ ] **Step 2: Write AssetUpload.tsx**

```typescript
import { useState } from "react";
import { Upload } from "lucide-react";
import { uploadProjectAssets } from "../../shared/api/projects";

const UPLOAD_ASSET_TYPES = [
  "profile",
  "pep",
  "transcriptome",
  "sample_summary",
  "group_spec",
  "ppt_template",
  "pdf_source",
  "raw_archive",
];

type Props = {
  projectId: string;
  onSuccess: () => void;
};

export function AssetUpload({ projectId, onSuccess }: Props) {
  const [assetType, setAssetType] = useState("profile");
  const [files, setFiles] = useState<File[]>([]);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleUpload = async () => {
    if (files.length === 0) return;
    setState("loading");
    setMessage("");
    try {
      const result = await uploadProjectAssets(projectId, {
        assetType,
        files,
        replaceExisting,
      });
      setState("idle");
      setMessage(
        `${result.assets.length} asset${result.assets.length !== 1 ? "s" : ""} uploaded.`
      );
      setFiles([]);
      onSuccess();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Upload failed");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "flex-end",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
      }}
    >
      <Field label="Asset type">
        <select
          value={assetType}
          onChange={(e) => setAssetType(e.target.value)}
          disabled={state === "loading"}
          style={inputStyle}
        >
          {UPLOAD_ASSET_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Files">
        <input
          type="file"
          multiple
          disabled={state === "loading"}
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
          style={inputStyle}
        />
      </Field>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--spacing-sm)",
          fontSize: "0.8rem",
          cursor: "pointer",
          paddingBottom: "2px",
        }}
      >
        <input
          type="checkbox"
          checked={replaceExisting}
          onChange={(e) => setReplaceExisting(e.target.checked)}
        />
        Replace existing
      </label>

      <button
        disabled={files.length === 0 || state === "loading"}
        onClick={handleUpload}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--spacing-sm)",
          padding: "10px 18px",
          borderRadius: "var(--radius-control)",
          background: "var(--accent)",
          color: "#ffffff",
          fontWeight: 500,
          opacity: files.length === 0 ? 0.5 : 1,
          cursor: files.length === 0 ? "default" : "pointer",
        }}
      >
        <Upload size={16} />
        {state === "loading" ? "Uploading…" : `Upload ${files.length || ""}`}
      </button>

      {message && (
        <p
          style={{
            width: "100%",
            margin: 0,
            fontSize: "0.85rem",
            color: state === "error" ? "var(--danger)" : "var(--success)",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "var(--text-secondary)",
        textTransform: "uppercase",
      }}
    >
      {label}
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/assets/
git commit -m "feat: add AssetTable and AssetUpload components"
```

---

### Task 9: Extract job feature components (JobSubmitForm, JobRow, JobList, JobResultPanel)

**Files:**
- Create: `frontend/src/features/jobs/JobSubmitForm.tsx`
- Create: `frontend/src/features/jobs/JobRow.tsx`
- Create: `frontend/src/features/jobs/JobList.tsx`
- Create: `frontend/src/features/jobs/JobResultPanel.tsx`

- [ ] **Step 1: Write JobSubmitForm.tsx**

```typescript
import { useState } from "react";
import { Send } from "lucide-react";
import { submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import type { JobModule } from "../../shared/types/domain";

const defaultPayload = JSON.stringify(
  {
    selected_modules: ["heatmap", "treemap", "chord"],
    samples: [],
    selected_chains: [],
    field_mapping: {},
  },
  null,
  2
);

type Props = {
  modules: JobModule[];
  projectId: string;
  onJobSubmitted?: (jobId: string) => void;
  onResultLoaded?: (result: JobResultsResponse) => void;
};

export function JobSubmitForm({
  modules,
  projectId,
  onJobSubmitted,
  onResultLoaded,
}: Props) {
  const [module, setModule] = useState(
    modules[0]?.key || "charts.combined"
  );
  const [payloadText, setPayloadText] = useState(defaultPayload);
  const [forceRerun, setForceRerun] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async () => {
    if (!module) return;
    setState("loading");
    setMessage("");
    try {
      const parsed = JSON.parse(payloadText || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("Payload must be a JSON object.");
      }
      const result = await submitJob({
        module,
        payload: parsed,
        projectId,
        forceRerun,
      });
      setState("idle");
      setMessage(
        result.reused_result
          ? `Reused cached result ${result.result_id || result.job_id}.`
          : `Submitted job ${result.job_id}.`
      );
      if (result.job_id) {
        onJobSubmitted?.(result.job_id);
        try {
          const jobResult = await getJobResults(result.job_id);
          onResultLoaded?.(jobResult);
        } catch {
          // result load is best-effort
        }
      }
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Submission failed");
    }
  };

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        padding: "var(--spacing-xl)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-md)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--spacing-md)",
        }}
      >
        <div>
          <h4 style={{ margin: 0 }}>Submit Job</h4>
          <p
            style={{
              margin: "2px 0 0",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
            }}
          >
            Unified API bridge
          </p>
        </div>
        <button
          disabled={state === "loading"}
          onClick={handleSubmit}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 20px",
            borderRadius: "var(--radius-control)",
            background: "var(--accent)",
            color: "#ffffff",
            fontWeight: 500,
            opacity: state === "loading" ? 0.7 : 1,
          }}
        >
          <Send size={16} />
          {state === "loading" ? "Submitting…" : "Submit"}
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1fr) auto",
          gap: "var(--spacing-md)",
          alignItems: "end",
        }}
      >
        <label
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "4px",
            fontSize: "0.75rem",
            fontWeight: 600,
            textTransform: "uppercase",
            color: "var(--text-secondary)",
          }}
        >
          Module
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            disabled={state === "loading"}
            style={{
              minHeight: "38px",
              padding: "7px 10px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
            }}
          >
            {(modules.length ? modules : [{ key: module, label: module }]).map(
              (m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              )
            )}
          </select>
        </label>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            fontSize: "0.85rem",
            cursor: "pointer",
            paddingBottom: "4px",
          }}
        >
          <input
            type="checkbox"
            checked={forceRerun}
            onChange={(e) => setForceRerun(e.target.checked)}
          />
          Force rerun
        </label>
      </div>

      <label
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "4px",
          fontSize: "0.75rem",
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-secondary)",
        }}
      >
        Payload JSON
        <textarea
          value={payloadText}
          onChange={(e) => setPayloadText(e.target.value)}
          disabled={state === "loading"}
          spellCheck={false}
          style={{
            minHeight: "150px",
            padding: "12px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            fontFamily: '"Cascadia Code", "Consolas", monospace',
            fontSize: "0.82rem",
            lineHeight: 1.5,
            resize: "vertical",
          }}
        />
      </label>

      {message && (
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color: state === "error" ? "var(--danger)" : "var(--success)",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write JobRow.tsx**

```typescript
import { StatusBadge } from "../../shared/components/StatusBadge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import type { JobSummary } from "../../shared/types/domain";

type Props = {
  job: JobSummary;
  onSelect?: (jobId: string) => void;
};

export function JobRow({ job, onSelect }: Props) {
  const jobId = job.job_id || job.id;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            marginBottom: "6px",
          }}
        >
          <strong style={{ fontSize: "0.9rem" }}>
            {job.module || job.job_type}
          </strong>
          <StatusBadge status={job.status} />
        </div>
        <ProgressBar value={Number(job.progress || 0)} />
        <div
          style={{
            fontSize: "0.75rem",
            color: "var(--text-tertiary)",
            marginTop: "4px",
          }}
        >
          {job.stage || job.detail || job.status}
        </div>
      </div>
      {onSelect && (job.status === "completed" || job.status === "failed") && (
        <button
          onClick={() => onSelect(jobId)}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--accent)",
            fontWeight: 500,
            fontSize: "0.8rem",
            whiteSpace: "nowrap",
          }}
        >
          Results
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write JobList.tsx**

```typescript
import { JobRow } from "./JobRow";
import { Skeleton } from "../../shared/components/Skeleton";
import type { JobSummary } from "../../shared/types/domain";

type Props = {
  jobs: JobSummary[];
  loading: boolean;
  emptyLabel?: string;
  onSelectResult?: (jobId: string) => void;
};

export function JobList({
  jobs,
  loading,
  emptyLabel = "No jobs found.",
  onSelectResult,
}: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
      {loading &&
        [1, 2, 3].map((i) => <Skeleton key={i} height="72px" />)}
      {!loading && jobs.length === 0 && (
        <p
          style={{
            color: "var(--text-tertiary)",
            textAlign: "center",
            padding: "var(--spacing-xl)",
          }}
        >
          {emptyLabel}
        </p>
      )}
      {jobs.map((job) => (
        <JobRow
          key={job.job_id || job.id}
          job={job}
          onSelect={onSelectResult}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Write JobResultPanel.tsx**

```typescript
import type { JobResultsResponse } from "../../shared/api/jobs";
import { StatusBadge } from "../../shared/components/StatusBadge";

type Props = {
  result: JobResultsResponse | null;
  loading: boolean;
};

export function JobResultPanel({ result, loading }: Props) {
  if (loading) {
    return (
      <div
        style={{
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-panel)",
          border: "1px solid var(--separator)",
          padding: "var(--spacing-xl)",
          textAlign: "center",
          color: "var(--text-tertiary)",
        }}
      >
        Loading job results…
      </div>
    );
  }

  if (!result) return null;

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        padding: "var(--spacing-xl)",
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
        <h4 style={{ margin: 0 }}>{result.job.module || "Job Result"}</h4>
        <StatusBadge status={result.status} />
      </div>

      {result.outputs.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              textTransform: "uppercase",
              color: "var(--text-secondary)",
              marginBottom: "var(--spacing-sm)",
            }}
          >
            Outputs
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {result.outputs.map((o) => (
              <a
                key={`${o.kind}-${o.url}`}
                href={o.url}
                target="_blank"
                rel="noreferrer"
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-pill)",
                  background: "var(--bg-root)",
                  color: "var(--accent)",
                  fontSize: "0.82rem",
                  fontWeight: 500,
                  textDecoration: "none",
                  border: "1px solid var(--separator)",
                }}
              >
                {o.label}
              </a>
            ))}
          </div>
        </div>
      )}

      {result.assets.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              textTransform: "uppercase",
              color: "var(--text-secondary)",
              marginBottom: "var(--spacing-sm)",
            }}
          >
            Registered Assets
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {result.assets.map((a) => (
              <a
                key={a.id}
                href={a.preview_url || "#"}
                target="_blank"
                rel="noreferrer"
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-pill)",
                  background: "var(--bg-root)",
                  color: "var(--text-primary)",
                  fontSize: "0.82rem",
                  textDecoration: "none",
                  border: "1px solid var(--separator)",
                }}
              >
                {a.original_name}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/jobs/
git commit -m "feat: add JobSubmitForm, JobRow, JobList, JobResultPanel components"
```

---

### Task 10: Create Dashboard page

**Files:**
- Create: `frontend/src/app/Dashboard.tsx`

- [ ] **Step 1: Write Dashboard.tsx**

```typescript
import { Boxes, FlaskConical, Activity } from "lucide-react";
import { useApi } from "../shared/hooks/useApi";
import { listProjects } from "../shared/api/projects";
import { listJobs } from "../shared/api/jobs";
import { MetricCard } from "../shared/components/MetricCard";
import { PageHeader } from "../shared/components/PageHeader";
import { ProjectList } from "../features/projects/ProjectList";
import { JobList } from "../features/jobs/JobList";
import { useNavigate } from "react-router-dom";

export function Dashboard() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects(), []);
  const jobs = useApi(() => listJobs({ limit: 5 }), []);

  const projectList =
    projects.status === "ready" ? projects.data.projects : [];
  const jobList = jobs.status === "ready" ? jobs.data.jobs : [];

  const stats = {
    projects: projectList.length,
    results: projectList.reduce(
      (sum, p) => sum + Number(p.result_count || 0),
      0
    ),
    activeJobs: jobList.filter(
      (j) => j.status === "running" || j.status === "queued"
    ).length,
  };

  return (
    <>
      <PageHeader
        title="Immune Repertoire Platform"
        subtitle="Database & ScriptHub analysis workspace"
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        <MetricCard icon={Boxes} label="Projects" value={stats.projects} color="var(--accent)" />
        <MetricCard
          icon={FlaskConical}
          label="Results"
          value={stats.results}
          color="var(--success)"
        />
        <MetricCard
          icon={Activity}
          label="Active Jobs"
          value={stats.activeJobs}
          color="var(--warning)"
        />
      </div>

      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--spacing-md)",
          }}
        >
          <h3 style={{ margin: 0 }}>Projects</h3>
          <button
            onClick={() => navigate("/database")}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-pill)",
              color: "var(--accent)",
              fontWeight: 500,
              fontSize: "0.85rem",
            }}
          >
            View all →
          </button>
        </div>
        <ProjectList />
      </div>

      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--spacing-md)",
          }}
        >
          <h3 style={{ margin: 0 }}>Recent Jobs</h3>
          <button
            onClick={() => navigate("/scripthub")}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-pill)",
              color: "var(--accent)",
              fontWeight: 500,
              fontSize: "0.85rem",
            }}
          >
            View all →
          </button>
        </div>
        <JobList
          jobs={jobList}
          loading={jobs.status === "loading"}
          emptyLabel="No jobs yet. Submit one from ScriptHub."
        />
      </div>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/Dashboard.tsx
git commit -m "feat: add Dashboard page with stats, projects and recent jobs"
```

---

### Task 11: Create Database page

**Files:**
- Create: `frontend/src/app/Database.tsx`

- [ ] **Step 1: Write Database.tsx**

```typescript
import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Database as DbIcon } from "lucide-react";
import { useApi } from "../shared/hooks/useApi";
import {
  getProject,
  listProjectAssets,
  listProjectResults,
} from "../shared/api/projects";
import type { PaginationInfo } from "../shared/components/Pagination";
import { PageHeader } from "../shared/components/PageHeader";
import { Pagination } from "../shared/components/Pagination";
import { Tabs } from "../shared/components/Tabs";
import { EmptyState } from "../shared/components/EmptyState";
import { AssetTable } from "../features/assets/AssetTable";
import { AssetUpload } from "../features/assets/AssetUpload";
import type { ProjectAsset } from "../shared/types/domain";

const ASSET_PAGE_SIZE = 10;

const TABS = [
  { key: "assets", label: "Assets" },
  { key: "results", label: "Results" },
];

export function DatabasePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState("assets");
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);

  const projectState = useApi(
    () => (projectId ? getProject(projectId) : Promise.resolve(null)),
    [projectId, refreshKey]
  );
  const assetsState = useApi(
    () =>
      projectId
        ? listProjectAssets(projectId, {
            page,
            pageSize: ASSET_PAGE_SIZE,
          })
        : Promise.resolve({ assets: [] as ProjectAsset[], pagination: undefined }),
    [projectId, page, refreshKey]
  );
  const resultsState = useApi(
    () =>
      projectId
        ? listProjectResults(projectId, { page: 1, pageSize: 50 })
        : Promise.resolve({ success: true, results: [] as ProjectAsset[] }),
    [projectId, refreshKey]
  );

  const handleUploadSuccess = useCallback(() => {
    setPage(1);
    setRefreshKey((k) => k + 1);
  }, []);

  if (!projectId) {
    return (
      <EmptyState
        icon={DbIcon}
        title="Select a Project"
        description="Choose a project from the Dashboard or navigate to a project URL."
        action={{ label: "Go to Dashboard", to: "/" }}
      />
    );
  }

  const project =
    projectState.status === "ready" ? projectState.data : null;
  const assets =
    assetsState.status === "ready" ? assetsState.data.assets : [];
  const pagination: PaginationInfo | undefined =
    assetsState.status === "ready"
      ? assetsState.data.pagination
      : undefined;
  const results =
    resultsState.status === "ready" ? resultsState.data.results : [];

  const loading = projectState.status === "loading";

  return (
    <>
      <PageHeader
        title={project?.name || "Loading…"}
        subtitle={
          project
            ? `${project.institution || "No institution"} · ${project.sample_count || 0} samples · ${project.result_count || 0} results`
            : "Project details"
        }
      >
        <button
          onClick={() => navigate("/")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "8px 16px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-secondary)",
            fontWeight: 500,
            fontSize: "0.85rem",
          }}
        >
          <ArrowLeft size={16} />
          All Projects
        </button>
      </PageHeader>

      <Tabs tabs={TABS} activeKey={tab} onChange={setTab} />

      {tab === "assets" && (
        <>
          <AssetUpload projectId={projectId} onSuccess={handleUploadSuccess} />
          <AssetTable
            assets={assets}
            loading={assetsState.status === "loading" || loading}
            emptyLabel="No assets registered for this project."
          />
          <Pagination
            pagination={pagination}
            onPageChange={setPage}
          />
        </>
      )}

      {tab === "results" && (
        <AssetTable
          assets={results}
          loading={resultsState.status === "loading" || loading}
          emptyLabel="No processed results for this project."
        />
      )}
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/Database.tsx
git commit -m "feat: add Database page with asset browser and result viewer"
```

---

### Task 12: Create ScriptHub page

**Files:**
- Create: `frontend/src/app/ScriptHub.tsx`

- [ ] **Step 1: Write ScriptHub.tsx**

```typescript
import { useState, useCallback, useMemo } from "react";
import { useApi } from "../shared/hooks/useApi";
import { usePolling } from "../shared/hooks/usePolling";
import { listJobs, listJobModules, getJobResults } from "../shared/api/jobs";
import { listProjects } from "../shared/api/projects";
import type { JobResultsResponse } from "../shared/api/jobs";
import { PageHeader } from "../shared/components/PageHeader";
import { JobSubmitForm } from "../features/jobs/JobSubmitForm";
import { JobList } from "../features/jobs/JobList";
import { JobResultPanel } from "../features/jobs/JobResultPanel";

export function ScriptHub() {
  const [resultJobId, setResultJobId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [resultState, setResultState] = useState<{
    result: JobResultsResponse | null;
    loading: boolean;
  }>({ result: null, loading: false });

  const modulesState = useApi(() => listJobModules(), []);
  const modules =
    modulesState.status === "ready" ? modulesState.data.modules : [];

  const projectsState = useApi(() => listProjects(), []);
  const projects =
    projectsState.status === "ready" ? projectsState.data.projects : [];

  // Auto-select first project if none selected
  useMemo(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  // Poll jobs filtered by selected project
  const allJobsState = usePolling(
    () => listJobs({ projectId: selectedProjectId || undefined, limit: 20 }),
    3000
  );
  const allJobs = allJobsState.data?.jobs || [];

  const activeJobs = allJobs.filter(
    (j) => j.status === "queued" || j.status === "running"
  );
  const recentJobs = allJobs.filter(
    (j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled"
  );

  const handleSelectResult = useCallback(async (jobId: string) => {
    setResultJobId(jobId);
    setResultState({ result: null, loading: true });
    try {
      const data = await getJobResults(jobId);
      setResultState({ result: data, loading: false });
    } catch {
      setResultState({ result: null, loading: false });
    }
  }, []);

  const handleJobSubmitted = useCallback((jobId: string) => {
    setResultJobId(jobId);
  }, []);

  const handleResultLoaded = useCallback((data: JobResultsResponse) => {
    setResultState({ result: data, loading: false });
  }, []);

  return (
    <>
      <PageHeader
        title="Script Hub"
        subtitle="Submit analysis jobs and monitor results"
      >
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          style={{
            minHeight: "38px",
            padding: "7px 12px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            fontSize: "0.85rem",
          }}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </PageHeader>

      <JobSubmitForm
        modules={modules}
        projectId={selectedProjectId}
        onJobSubmitted={handleJobSubmitted}
        onResultLoaded={handleResultLoaded}
      />

      {activeJobs.length > 0 && (
        <div>
          <h3 style={{ marginBottom: "var(--spacing-md)" }}>Active Jobs</h3>
          <JobList
            jobs={activeJobs}
            loading={allJobsState.loading && activeJobs.length === 0}
            emptyLabel="No active jobs."
          />
        </div>
      )}

      {resultState.result && (
        <div>
          <h3 style={{ marginBottom: "var(--spacing-md)" }}>Job Result</h3>
          <JobResultPanel
            result={resultState.result}
            loading={resultState.loading}
          />
        </div>
      )}

      <div>
        <h3 style={{ marginBottom: "var(--spacing-md)" }}>Recent Jobs</h3>
        <JobList
          jobs={recentJobs}
          loading={allJobsState.loading && recentJobs.length === 0}
          emptyLabel="No completed jobs."
          onSelectResult={handleSelectResult}
        />
      </div>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/ScriptHub.tsx
git commit -m "feat: add ScriptHub page with job submission and monitoring"
```

---

### Task 13: Verify build and typecheck

**Files:** (none — verification only)

- [ ] **Step 1: Run TypeScript type check**

```bash
cd frontend && npx tsc -b
```

Expected: Exit code 0, no type errors.

- [ ] **Step 2: Run Vite build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds. `frontend/dist/` contains `index.html` + hashed JS/CSS assets.

- [ ] **Step 3: Fix any build errors**

If build fails, fix the reported errors before proceeding. Common issues:
- Missing imports (ensure all component imports match actual file paths)
- Type mismatches (ensure API response types match `domain.ts` types)
- Unused variables (remove or prefix with `_`)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete frontend modular redesign with Apple-style design system"
```

---

## Self-Review

| Check | Status |
|-------|--------|
| All spec sections covered | ✅ Dashboard, Database, ScriptHub, design tokens, components, hooks, routing |
| No placeholders in any task | ✅ Every step has complete code or exact commands |
| Type consistency across tasks | ✅ `PaginationInfo`, `JobResultsResponse`, `JobSummary`, `ProjectAsset`, `ProjectSummary`, `JobModule` all match domain.ts and API modules |
| File paths match spec structure | ✅ All paths verified against spec file tree |
| Components match spec inventory | ✅ All 11 shared components + all feature components |
| Design tokens match spec | ✅ Colors, radii, animations, typography, spacing all match |
