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
