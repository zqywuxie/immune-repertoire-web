export type TableSort = { column: number | null; direction: "asc" | "desc"; mode: "text" | "numeric" };
export const originalOrder: TableSort = { column: null, direction: "asc", mode: "text" };

function numberParts(value: string) {
  const match = value.trim().match(/^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/);
  if (!match) return null;
  const fraction = match[3] ?? match[4] ?? "";
  const all = (match[2] || "") + fraction;
  const withoutLeading = all.replace(/^0+/, "");
  if (!withoutLeading) return { sign: 0, order: 0n, digits: "" };
  return { sign: match[1] === "-" ? -1 : 1, order: BigInt(withoutLeading.length - fraction.length) + BigInt(match[5] || "0"), digits: withoutLeading.replace(/0+$/, "") };
}

export function compareTableValues(left: string, right: string, mode: TableSort["mode"], direction: TableSort["direction"]) {
  const reverse = direction === "desc" ? -1 : 1;
  if (mode === "text") {
    left = left.toLocaleLowerCase(); right = right.toLocaleLowerCase();
    return (left < right ? -1 : left > right ? 1 : 0) * reverse;
  }
  const a = numberParts(left), b = numberParts(right);
  // Empty, NA and other non-numeric values remain last in both directions.
  if (!a || !b) return a ? -1 : b ? 1 : 0;
  if (a.sign !== b.sign) return (a.sign - b.sign) * reverse;
  if (a.sign === 0) return 0;
  let magnitude = a.order < b.order ? -1 : a.order > b.order ? 1 : 0;
  if (!magnitude) {
    const size = Math.max(a.digits.length, b.digits.length);
    const x = a.digits.padEnd(size, "0"), y = b.digits.padEnd(size, "0");
    magnitude = x < y ? -1 : x > y ? 1 : 0;
  }
  return magnitude * a.sign * reverse;
}

export function sortTableRows(rows: string[][], sort: TableSort) {
  if (sort.column === null) return rows;
  const column = sort.column;
  return rows.map((row, index) => ({row, index})).sort((a, b) =>
    compareTableValues(a.row[column] || "", b.row[column] || "", sort.mode, sort.direction) || a.index - b.index
  ).map(item => item.row);
}

export function toggleTableSort(sort: TableSort, column: number): TableSort {
  if (sort.column !== column) return {...sort, column, direction: "asc"};
  return sort.direction === "asc" ? {...sort, direction: "desc"} : {...sort, column: null, direction: "asc"};
}
