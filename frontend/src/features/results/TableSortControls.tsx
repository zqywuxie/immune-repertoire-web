import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { toggleTableSort, type TableSort } from "./tableSorting";
import "./TableSorting.css";

export function TableSortControls({sort, onChange, disabled}: {sort: TableSort; onChange: (sort: TableSort) => void; disabled?: boolean}) {
  return <div className="table-sort-controls">
    <label>排序方式 <select aria-label="排序方式" value={sort.mode} disabled={disabled} onChange={event => onChange({...sort, mode: event.target.value as TableSort["mode"]})}>
      <option value="text">文本</option><option value="numeric">数值（含科学计数法）</option>
    </select></label>
    <span>{sort.mode === "numeric" ? "点击列名排序；空值和非数值在末尾。" : "点击列名排序，再次点击切换降序。"}</span>
    {sort.column !== null && <button type="button" disabled={disabled} onClick={() => onChange({...sort, column: null, direction: "asc"})}>恢复原始顺序</button>}
  </div>;
}

export function TableSortHead({columns, sort, onChange, disabled}: {columns: string[]; sort: TableSort; onChange: (sort: TableSort) => void; disabled?: boolean}) {
  return <thead><tr>{columns.map((column, index) => {
    const selected = sort.column === index, label = column || "第 " + (index + 1) + " 列";
    return <th scope="col" key={index} aria-sort={selected ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" aria-label={"按" + label + "排序"} disabled={disabled} onClick={() => onChange(toggleTableSort(sort, index))}>
        <span>{label}</span>{selected ? (sort.direction === "asc" ? <ArrowUp size={14} aria-hidden="true" /> : <ArrowDown size={14} aria-hidden="true" />) : <ArrowUpDown size={14} aria-hidden="true" />}
      </button>
    </th>;
  })}</tr></thead>;
}
