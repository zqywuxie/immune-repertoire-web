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
    return <p style={{ color: "var(--text-tertiary)", fontSize: "0.875rem" }}>暂无分页数据</p>;
  }

  const { page, total, total_pages } = pagination;
  const last = Math.max(total_pages, 1);
  const numbers = [...new Set([1, last, ...Array.from({ length: 5 }, (_, index) => page + index - 2).filter(value => value >= 1 && value <= last)])].sort((a, b) => a - b);
  const pages: (number | string)[] = [];
  numbers.forEach((value, index) => { if (index && value - numbers[index - 1] > 1) pages.push(`gap-${value}`); pages.push(value); });

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--spacing-md)",
        color: "var(--text-secondary)",
        fontSize: "0.875rem",
      }}
    >
      <span>
        共 {total} 项 · 第 {page} / {Math.max(total_pages, 1)} 页
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
        <PageBtn disabled={page <= 1} onClick={() => onPageChange(page - 1)} ariaLabel="上一页">
          ←
        </PageBtn>
        {pages.map((p) => typeof p === "string" ? <span key={p} aria-hidden="true" style={{ padding: "8px 3px" }}>…</span> : (
          <PageBtn
            key={p}
            active={p === page}
            onClick={() => onPageChange(p)}
            ariaLabel={`第 ${p} 页`}
          >
            {p}
          </PageBtn>
        ))}
        <PageBtn
          disabled={page >= total_pages}
          onClick={() => onPageChange(page + 1)}
          ariaLabel="下一页"
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
  ariaLabel,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  active?: boolean;
  onClick: () => void;
  ariaLabel?: string;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel}
      aria-current={active ? "page" : undefined}
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
