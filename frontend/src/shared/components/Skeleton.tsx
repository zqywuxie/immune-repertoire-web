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
