import { useState, useEffect, type CSSProperties, type ReactNode } from "react";
import { Search, ChevronDown, ChevronRight, SlidersHorizontal } from "lucide-react";
import { SampleIdentifierFilter } from "./SampleIdentifierFilter";
import { Sheet } from "../../shared/components/Sheet";
import { useMediaQuery } from "../../shared/hooks/useMediaQuery";
import type { ListSamplesParams } from "../../shared/api/samples";
import { canonicalSpecies, speciesLabel, speciesOptions, healthyLabel, pairedLabel } from "./sampleDisplay";

type FilterProps = {fieldOptions:Record<string,string[]>;filters:ListSamplesParams;searchText:string;
  onFilterChange:(key:keyof ListSamplesParams,value:string)=>void;onSearchChange:(value:string)=>void;
  onClear:()=>void;hasActiveFilters:boolean;onApplyFilters:(filters:ListSamplesParams)=>void};

export function SampleFilters(props: FilterProps) {
  const mobile = useMediaQuery("(max-width: 768px)");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ListSamplesParams>({});
  useEffect(() => { if (!mobile) setOpen(false); }, [mobile]);
  if (!mobile) return <FilterToolbar {...props}/>;
  const count = Object.entries(props.filters).filter(([key,value]) => value && !["project_id","asset_set","page","page_size"].includes(key)).length;
  return <>
    <ActiveSampleFilters filters={props.filters} onFilterChange={props.onFilterChange}/>
    <div className="data-mobile-query"><input className="input" aria-label="搜索样本" placeholder="搜索样本…" value={props.searchText} onChange={event=>props.onSearchChange(event.target.value)}/>
      <button className="btn btn-secondary" aria-label={`筛选条件（${count}）`} onClick={()=>{setDraft({...props.filters});setOpen(true);}}><SlidersHorizontal size={16}/>筛选{count ? `（${count}）` : ""}</button></div>
    <Sheet open={open} onClose={()=>setOpen(false)} title="样本筛选">
      <div className="data-mobile-filter-controls"><p className="data-muted">选择条件后应用到当前项目和数据集。关闭不会改变已生效的筛选。</p>
        <FilterToolbar fieldOptions={props.fieldOptions} filters={draft} searchText="" onSearchChange={()=>{}} showChips={false} hideSearch expanded
          onFilterChange={(key,value)=>setDraft(previous=>({...previous,[key]:value}))} hasActiveFilters={false}
          onClear={()=>setDraft({project_id:props.filters.project_id,asset_set:props.filters.asset_set})}/></div>
      <div className="data-filter-footer"><button className="btn btn-secondary" onClick={()=>setDraft({project_id:props.filters.project_id,asset_set:props.filters.asset_set})}>重置条件</button>
        <button className="btn btn-primary" onClick={()=>{props.onApplyFilters(draft);setOpen(false);}}>应用筛选</button></div>
    </Sheet>
  </>;
}

function ActiveSampleFilters({filters,onFilterChange}:{filters:ListSamplesParams;onFilterChange:FilterProps["onFilterChange"]}) {
  return <div className="data-active-filters" aria-label="生效筛选条件">{Object.entries(filters).filter(([key,value]) => value && !["project_id","asset_set","page","page_size"].includes(key)).map(([key,value]) => {
        const labels: Record<string,string> = {project_name:"项目",sample_id:"样本编号",sample_name:"名称",chain_flag:"链类型",is_healthy:"健康状态",spices:"物种",is_pe:"双端测序",sequence_id:"序列编号",institution:"机构",contain_method:"纳入方法",iso_tag:"同型标签",illness:"疾病"};
        const values = key === "spices" ? [...new Set(String(value).split(",").filter(Boolean).map(canonicalSpecies))]
          : key === "illness" ? [...new Set(String(value).split(",").filter(Boolean))] : [String(value)];
        return values.map(item => {
          const text = key === "spices" ? speciesLabel(item) : key === "is_healthy" ? healthyLabel(item) : key === "is_pe" ? pairedLabel(item) : item;
          return <button className="data-filter-chip" key={`${key}:${item}`} aria-label={`移除${labels[key] || key}筛选：${text}`} onClick={() => {
            const remaining = values.filter(value => value !== item);
            onFilterChange(key as keyof ListSamplesParams, remaining.join(","));
          }}>{labels[key] || key}：{text}<span aria-hidden="true">×</span></button>;
        });
      })}</div>;
}

function FilterToolbar({
  expanded = false,
  hideSearch = false,
  showChips = true,
  fieldOptions,
  filters,
  searchText,
  onFilterChange,
  onSearchChange,
  onClear,
  hasActiveFilters,
}: {
  expanded?: boolean; hideSearch?: boolean; showChips?: boolean;
  fieldOptions: Record<string, string[]>;
  filters: ListSamplesParams;
  searchText: string;
  onFilterChange: (key: keyof ListSamplesParams, value: string) => void;
  onSearchChange: (v: string) => void;
  onClear: () => void;
  hasActiveFilters: boolean;
}) {
  const [showAdvanced, setShowAdvanced] = useState(expanded || !!(filters.sequence_id || filters.institution || filters.contain_method || filters.iso_tag || filters.illness));
  const [selectedSpecies, setSelectedSpecies] = useState(() => [...new Set((filters.spices || "").split(",").filter(Boolean).map(canonicalSpecies))]);
  useEffect(() => { setSelectedSpecies([...new Set((filters.spices || "").split(",").filter(Boolean).map(canonicalSpecies))]); }, [filters.spices]);

  const [selectedIllness, setSelectedIllness] = useState(() => (filters.illness || "").split(",").filter(Boolean));
  const [illnessDraft, setIllnessDraft] = useState("");
  useEffect(() => { setSelectedIllness((filters.illness || "").split(",").filter(Boolean)); }, [filters.illness]);
  function changeIllness(values: string[]) { setSelectedIllness(values); onFilterChange("illness", values.join(",")); }
  function addIllness() {
    const values = illnessDraft.split(/[,，、]/).map(value => value.trim()).filter(Boolean);
    if (!values.length) return;
    changeIllness([...new Set([...selectedIllness, ...values])]); setIllnessDraft("");
  }

  const hasAdvancedFilters =
    !!filters.sequence_id ||
    !!filters.institution ||
    !!filters.contain_method ||
    !!filters.iso_tag ||
    !!filters.illness;

  const allHasActive = hasActiveFilters || hasAdvancedFilters || !!searchText;

  return (
    <div className="data-filter-toolbar"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-md)",
        marginBottom: "var(--spacing-lg)",
        padding: "var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
      }}
    >
      {showChips && <ActiveSampleFilters filters={filters} onFilterChange={onFilterChange}/>}
      {/* Basic filters row */}
      <div className="data-filter-basic"
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "var(--spacing-md)",
        }}
      >
        {/* Search input */}
        {!hideSearch && (<div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", flex: "1 1 240px", maxWidth: "320px" }}>
          <Search size={16} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
          <input
            type="text"
            value={searchText}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索样本…"
            style={filterInputStyle}
            aria-label="搜索样本"
          />
        </div>)}

        {/* Filter selects */}
        {!filters.project_id && <FilterSelect
          label="项目"
          value={filters.project_name || ""}
          onChange={(v) => onFilterChange("project_name", v)}
        >
          <option value="">全部项目</option>
          {(fieldOptions.project_name || []).map(value => <option key={value} value={value}>{value}</option>)}
        </FilterSelect>}

        <SampleIdentifierFilter key={JSON.stringify([filters.project_id,filters.asset_set,"sample_id"])} field="sample_id" label="样本编号" value={filters.sample_id || ""} projectId={filters.project_id || ""} dataset={filters.asset_set || ""} onChange={value=>onFilterChange("sample_id",value)}/>

        <FilterSelect
          label="链类型"
          value={filters.chain_flag || ""}
          onChange={(v) => onFilterChange("chain_flag", v)}
        >
          <option value="">全部链</option>
          <option value="TRA">TRA</option>
          <option value="TRB">TRB</option>
          <option value="TRG">TRG</option>
          <option value="TRD">TRD</option>
          <option value="IGH">IGH</option>
          <option value="IGK">IGK</option>
          <option value="IGL">IGL</option>
        </FilterSelect>

        <FilterSelect
          label="健康状态"
          value={filters.is_healthy || ""}
          onChange={(v) => onFilterChange("is_healthy", v)}
        >
          <option value="">全选</option>
          <option value="yes">健康</option>
          <option value="no">非健康</option>
        </FilterSelect>

        <details className="data-multi-filter">
          <summary>物种 · {selectedSpecies.length ? selectedSpecies.map(speciesLabel).join("、") : "全部物种"}</summary>
          <fieldset aria-label="物种多选"><legend>可同时选择多个物种</legend>
            {speciesOptions([...(fieldOptions.spices || []), ...(filters.spices || "").split(",").filter(Boolean)]).map(item => {
              const selected = selectedSpecies;
              return <label key={item.value}><input type="checkbox" checked={selected.includes(item.value)}
                onChange={event => { const next = event.target.checked ? [...selected,item.value] : selected.filter(value => value !== item.value); setSelectedSpecies(next); onFilterChange("spices", next.join(",")); }} />{item.label}</label>;
            })}
          </fieldset>
        </details>

        <FilterSelect
          label="双端测序"
          value={filters.is_pe || ""}
          onChange={(v) => onFilterChange("is_pe", v)}
        >
          <option value="">全选</option>
          <option value="yes">是</option>
          <option value="no">否</option>
        </FilterSelect>

        {allHasActive && !expanded && (
          <button
            onClick={onClear}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--text-secondary)",
              fontSize: "0.8rem",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            清空筛选
          </button>
        )}
      </div>

      {/* Advanced filters toggle */}
      <div>
        {!expanded && <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: 0,
            border: "none",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: "0.8rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          高级筛选
          {hasAdvancedFilters && (
            <span style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "18px",
              height: "18px",
              borderRadius: "50%",
              background: "var(--accent)",
              color: "#fff",
              fontSize: "0.65rem",
              fontWeight: 700,
            }}>
              •
            </span>
          )}
        </button>}

        {showAdvanced && (
          <div className="data-filter-advanced"
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "var(--spacing-md)",
              marginTop: "var(--spacing-md)",
              paddingTop: "var(--spacing-md)",
              borderTop: "1px solid var(--separator)",
            }}
          >
            <SampleIdentifierFilter key={JSON.stringify([filters.project_id,filters.asset_set,"sequence_id"])} field="sequence_id" label="序列编号" value={filters.sequence_id || ""} projectId={filters.project_id || ""} dataset={filters.asset_set || ""} onChange={value=>onFilterChange("sequence_id",value)}/>

            <FilterSelect
              label="所属机构"
              value={filters.institution || ""}
              onChange={(v) => onFilterChange("institution", v)}
            >
              <option value="">全选</option>
              {(fieldOptions.institution || []).map(value => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>

            <FilterSelect
              label="纳入方法"
              value={filters.contain_method || ""}
              onChange={(v) => onFilterChange("contain_method", v)}
            >
              <option value="">全选</option>
              {(fieldOptions.contain_method || []).map(value => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>

            <FilterSelect
              label="同型标签"
              value={filters.iso_tag || ""}
              onChange={(v) => onFilterChange("iso_tag", v)}
            >
              <option value="">全选</option>
              {(fieldOptions.iso_tag || []).map(value => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>

            <details className="data-multi-filter">
              <summary>疾病 · {selectedIllness.length ? selectedIllness.join("、") : "全部疾病"}</summary>
              <fieldset aria-label="疾病多选"><legend>可同时选择多个疾病</legend>
                {[...new Set([...(fieldOptions.illness || []), ...selectedIllness])].map(value => <label key={value}>
                  <input type="checkbox" checked={selectedIllness.includes(value)} onChange={event => changeIllness(event.target.checked ? [...selectedIllness,value] : selectedIllness.filter(item=>item!==value))} />{value}
                </label>)}
                {!fieldOptions.illness?.length && !selectedIllness.length && <p className="data-muted">当前范围暂无疾病候选，可添加自定义值。</p>}
              </fieldset>
              <div className="data-query-bar"><input className="input" aria-label="添加自定义疾病筛选" value={illnessDraft} onChange={event=>setIllnessDraft(event.target.value)}
                placeholder="输入疾病名称" onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();addIllness();}}} />
                <button className="btn btn-secondary" disabled={!illnessDraft.trim()} onClick={addIllness}>添加条件</button></div>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "2px",
        fontSize: "0.7rem",
        fontWeight: 600,
        textTransform: "uppercase",
        color: "var(--text-tertiary)",
        minWidth: "110px",
      }}
    >
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={filterSelectStyle}
      >
        {children}
      </select>
    </label>
  );
}

const filterInputStyle: CSSProperties = {
  flex: 1,
  minHeight: "36px",
  padding: "6px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};

const filterSelectStyle: CSSProperties = {
  minHeight: "36px",
  padding: "5px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.82rem",
  cursor: "pointer",
};
