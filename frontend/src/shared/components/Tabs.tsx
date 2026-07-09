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
  const tabRefs = tabs.map(() => ({ current: null as HTMLButtonElement | null }));

  function moveFocus(from: number, delta: number) {
    const next = from + delta;
    if (next >= 0 && next < tabs.length) {
      tabRefs[next].current?.focus();
    }
  }

  function handleKeyDown(index: number, e: React.KeyboardEvent) {
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        if (index > 0) tabRefs[index - 1].current?.focus();
        else tabRefs[tabs.length - 1].current?.focus();
        break;
      case "ArrowRight":
        e.preventDefault();
        if (index < tabs.length - 1) tabRefs[index + 1].current?.focus();
        else tabRefs[0].current?.focus();
        break;
      case "Home":
        e.preventDefault();
        tabRefs[0].current?.focus();
        break;
      case "End":
        e.preventDefault();
        tabRefs[tabs.length - 1].current?.focus();
        break;
    }
  }

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
      {tabs.map((tab, idx) => {
        const isActive = tab.key === activeKey;
        return (
          <button
            key={tab.key}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            onKeyDown={(e) => handleKeyDown(idx, e)}
            ref={tabRefs[idx]}
            tabIndex={isActive ? 0 : -1}
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
