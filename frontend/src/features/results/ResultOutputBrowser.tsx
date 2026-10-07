import { useEffect, useMemo, useState } from "react";
import { FileText, Image as ImageIcon, Search } from "lucide-react";
import { kindLabel } from "./ResultViewer";
import { comparisonLabel, organizeOutput, type BrowseOutput, type ResultComparison } from "./resultOrganization";
import "./ResultOutputBrowser.css";
import { defaultResultFilters, type ResultBrowseFilters } from "./resultAddress";

const pageSize = 12;
type Filters = ResultBrowseFilters;
const initialFilters = defaultResultFilters;

export function ResultOutputBrowser({ outputs, selectedKey, onSelect, storageKey, comparisons, addressFilters, onFiltersChange }: {
  outputs: BrowseOutput[]; selectedKey: string; onSelect: (key: string) => void; storageKey: string; comparisons: ResultComparison[];
  addressFilters?: Filters; onFiltersChange?: (filters: Filters) => void;
}) {
  const organized = useMemo(() => outputs.map(item => organizeOutput(item, comparisons)), [outputs, comparisons]);
  const [filters, setFilters] = useState<Filters>(() => {
    if (addressFilters) return addressFilters;
    try {
      const stored = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      if (stored) return { query: String(stored.query || ""), content: String(stored.content || ""), chain: String(stored.chain || ""), comparison: String(stored.comparison || ""), page: Math.max(0, Math.floor(Number(stored.page) || 0)), thumbnails: stored.thumbnails === true };
    } catch { /* Storage is optional. */ }
    return { ...initialFilters, page: Math.floor(Math.max(0, outputs.findIndex(item => item.key === selectedKey)) / pageSize) };
  });
  const addressValue = addressFilters ? JSON.stringify(addressFilters) : "";
  useEffect(() => { if (addressValue) setFilters(JSON.parse(addressValue)); }, [addressValue]);
  const update = (next: Partial<Filters>) => {
    const value = { ...filters, ...next };
    setFilters(value);
    onFiltersChange?.(value);
    try { sessionStorage.setItem(storageKey, JSON.stringify(value)); } catch { /* Browser remains usable. */ }
  };
  const options = (values: string[]) => [...new Set(values.filter(Boolean))];
  const contents = options(organized.map(item => item.content));
  const chains = options(organized.flatMap(item => item.chains));
  const comparisonKeys = options(organized.map(item => item.comparison));
  // Removed outputs must not leave restored filters stuck at an unavailable value.
  const content = contents.includes(filters.content) ? filters.content : "";
  const chain = chains.includes(filters.chain) || filters.chain === "unassigned" ? filters.chain : "";
  const comparison = comparisonKeys.includes(filters.comparison) || filters.comparison === "unassigned" ? filters.comparison : "";
  const query = filters.query.trim().toLocaleLowerCase();
  const filtered = organized.filter(item => (!content || item.content === content)
    && (!chain || (chain === "unassigned" ? !item.chains.length : item.chains.includes(chain)))
    && (!comparison || (comparison === "unassigned" ? !item.comparison : item.comparison === comparison))
    && (!query || [item.label, item.content, item.chains.join(" "), comparisonLabel(item.comparison, comparisons), item.url.split("?")[0]].join(" ").toLocaleLowerCase().includes(query)));
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const page = Math.min(filters.page, pages - 1);
  const visible = filtered.slice(page * pageSize, (page + 1) * pageSize);
  return <div className="result-output-browser">
    <div className="result-browser-toolbar">
      <label className="result-browser-search"><span>查找图表或报告</span><div><Search size={16} aria-hidden="true" /><input aria-label="查找图表或报告" value={filters.query} placeholder="输入指标、链或比较名称" onChange={event => update({query: event.target.value, page: 0})} /></div></label>
      <label><span>分析内容</span><select aria-label="分析内容" value={content} onChange={event => update({content: event.target.value, page: 0})}><option value="">全部内容</option>{contents.map(value => <option key={value}>{value}</option>)}</select></label>
      {chains.length > 0 && <label><span>受体链</span><select aria-label="受体链" value={chain} onChange={event => update({chain: event.target.value, page: 0})}><option value="">全部链</option>{chains.map(value => <option key={value}>{value}</option>)}<option value="unassigned">未标注链</option></select></label>}
      {comparisonKeys.length > 0 && <label><span>组间比较</span><select aria-label="组间比较" value={comparison} onChange={event => update({comparison: event.target.value, page: 0})}><option value="">全部比较</option>{comparisonKeys.map(value => <option key={value} value={value}>{comparisonLabel(value, comparisons)}</option>)}<option value="unassigned">未标注比较</option></select></label>}
    </div>
    <div className="result-browser-summary">
      <span role="status">找到 {filtered.length} 个结果，共 {outputs.length} 个</span>
      <label className="result-browser-toggle"><input type="checkbox" checked={filters.thumbnails} onChange={event => update({thumbnails: event.target.checked})} />显示缩略图</label>
      {(filters.query || content || chain || comparison) && <button type="button" onClick={() => update({...initialFilters, thumbnails: filters.thumbnails})}>清除筛选</button>}
    </div>
    {visible.length ? <div className="result-browser-grid" aria-label="图表与报告列表">
      {visible.map(item => <button type="button" key={item.key} className="result-browser-card" aria-pressed={item.key === selectedKey} onClick={() => onSelect(item.key)}>
        <Thumbnail key={item.url + String(filters.thumbnails)} url={item.url} kind={item.kind} enabled={filters.thumbnails} />
        <strong>{item.label || kindLabel(item.kind)}</strong>
        <span className="result-browser-tags"><span>{item.content}</span>{item.chains.map(value => <span key={value}>{value}</span>)}{item.comparison && <span>{comparisonLabel(item.comparison, comparisons)}</span>}</span>
        <span className="result-browser-kind">{item.key === selectedKey ? "正在查看 · " : ""}{kindLabel(item.kind)}</span>
      </button>)}
    </div> : <p className="result-browser-empty">没有匹配的结果，请调整或清除筛选。</p>}
    {pages > 1 && <nav className="result-browser-pagination" aria-label="图表列表分页">
      <button type="button" disabled={page === 0} onClick={() => update({page: page - 1})}>上一页</button><span>第 {page + 1} / {pages} 页</span><button type="button" disabled={page === pages - 1} onClick={() => update({page: page + 1})}>下一页</button>
    </nav>}
  </div>;
}

function Thumbnail({url, kind, enabled}: {url: string; kind: string; enabled: boolean}) {
  const [failed, setFailed] = useState(false);
  const image = ["png", "jpg", "jpeg", "svg", "image"].includes(kind);
  if (!enabled || !image) return <span className="result-browser-icon" aria-hidden="true">{image ? <ImageIcon size={22} /> : <FileText size={22} />}</span>;
  return <span className="result-browser-thumbnail">{failed ? <span>缩略图不可用，点击查看文件</span> : <img src={url} alt="" aria-hidden="true" loading="lazy" onError={() => setFailed(true)} />}</span>;
}
