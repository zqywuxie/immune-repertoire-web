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
