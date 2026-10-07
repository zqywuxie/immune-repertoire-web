import { useState, useEffect, useRef } from "react";
import {
  FolderOpen,
  Database,
  FileText,
  BarChart3,
  FileSpreadsheet,
  Trash2,
  CheckCircle2,
  Layers,
  ChevronDown,
  ChevronRight,
  FolderTree,
} from "lucide-react";
import { useApi } from "../../../shared/hooks/useApi";
import { getProject } from "../../../shared/api/projects";
import type { ProjectAsset } from "../../../shared/types/domain";
import { Skeleton } from "../../../shared/components/Skeleton";
import { EmptyState } from "../../../shared/components/EmptyState";
import { ProjectPicker } from "../../projects/ProjectPicker";
import { Card } from "../../../shared/components/Card";
import { Select } from "../../../shared/components/Select";
import { DirectoryBrowser } from "../../../shared/components/DirectoryBrowser";
import { assetPath, getAssetSetName, isInputAsset } from "../../assets/assetSets";
import { inputDataForAsset } from "../../analysis/InputAssetIntent";
import { useAnalysisInputSelection } from "../../analysis/useAnalysisInputSelection";
import { AssetUpload } from "../../assets/AssetUpload";

export type BasketKey = "pep" | "profile" | "transcriptome" | "deconvolution";

export interface Stage1UpdateData {
  projectId: string;
  assetSetName: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  deconvolutionPath?: string;
  inputAssets?: ProjectAsset[];
  selectionExplicit?: boolean;
}

interface Stage1DataIntakeProps {
  requestedAsset?: ProjectAsset;
  allowDefaultDataset?: boolean;
  inputIntentPending?: boolean;
  assetSetName?: string;
  inputAssets?: ProjectAsset[];
  selectionExplicit?: boolean;
  projectId: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  deconvolutionPath?: string;
  onUpdate: (data: Stage1UpdateData, asset?: ProjectAsset) => void;
}

export function Stage1DataIntake({
  requestedAsset,
  allowDefaultDataset = true,
  inputIntentPending = false,
  assetSetName = "",
  projectId,
  pepPaths,
  profilePath,
  transcriptomePath,
  deconvolutionPath = "",
  onUpdate: onSelectionUpdate,
  inputAssets = [],
  selectionExplicit = false,
}: Stage1DataIntakeProps) {
  const [selectedProjectId, setSelectedProjectId] = useState(projectId);
  const [selectedSetName, setSelectedSetName] = useState(assetSetName);
  useEffect(() => { setSelectedSetName(assetSetName); }, [assetSetName]);
  const [showBrowser, setShowBrowser] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [showAllClones,setShowAllClones]=useState(false);
  const autoSelectedProject = useRef("");
  const pendingDataset = useRef("");
  const appliedIntent = useRef("");
  const [selectionError,setSelectionError] = useState("");
  const [selectedVersions,setSelectedVersions] = useState<Record<string,ProjectAsset>>({});
  useEffect(()=>{if(requestedAsset)setSelectedVersions(previous=>previous[requestedAsset.id]===requestedAsset?previous:{...previous,[requestedAsset.id]:requestedAsset});},[requestedAsset]);

  const selectedPaths = new Set([...pepPaths,profilePath,transcriptomePath,deconvolutionPath]);
  const pinned = [...inputAssets,...Object.values(selectedVersions)].filter(asset=>asset.project_id===selectedProjectId && selectedPaths.has(assetPath(asset)));
  const inputs=useAnalysisInputSelection(selectedProjectId,selectedSetName || (requestedAsset?getAssetSetName(requestedAsset):""),[...pinned,...(requestedAsset?[requestedAsset]:[])],0,allowDefaultDataset);
  const dataSets=inputs.sets;
  const allAssets=inputs.selected.assets;
  const selectedAssetByPath=new Map(allAssets.map(asset=>[assetPath(asset),asset]));
  function onUpdate(next:Stage1UpdateData, selectedAsset?:ProjectAsset) {
    const paths=new Set([...next.pepPaths,next.profilePath,next.transcriptomePath,next.deconvolutionPath]);
    const refs=[...new Map([...allAssets,...(selectedAsset?[selectedAsset]:[])].map(asset=>[asset.id,asset])).values()]
      .filter(asset=>asset.project_id===next.projectId && getAssetSetName(asset)===next.assetSetName && paths.has(assetPath(asset)));
    const selection={...next,inputAssets:refs,selectionExplicit:true};
    if(selectedAsset)onSelectionUpdate(selection,selectedAsset);else onSelectionUpdate(selection);
  }
  const assetsLoading = inputs.loading;

  const projectDetailState = useApi(
    () => selectedProjectId ? getProject(selectedProjectId, { summaryOnly: true }) : Promise.resolve(null as any),
    [selectedProjectId],
  );
  const projectDetail = projectDetailState.status === "ready" ? projectDetailState.data : null;

  useEffect(()=>{
    if(!requestedAsset){appliedIntent.current="";return;}
    if(inputIntentPending || !inputs.ready || appliedIntent.current===requestedAsset.id)return;
    const sourceSet=dataSets.find(set=>set.name===getAssetSetName(requestedAsset));
    if(!sourceSet)return;
    appliedIntent.current=requestedAsset.id;autoSelectedProject.current=selectedProjectId;
    const preserveSelection=projectId===selectedProjectId && assetSetName===sourceSet.name && Boolean(pepPaths.length || profilePath || transcriptomePath || deconvolutionPath);
    const base=preserveSelection ? {projectId:selectedProjectId,assetSetName:sourceSet.name,pepPaths,profilePath,transcriptomePath,deconvolutionPath} : {projectId:selectedProjectId,assetSetName:sourceSet.name,pepPaths:sourceSet.pepPaths,profilePath:sourceSet.profilePath,transcriptomePath:sourceSet.transcriptomePath,deconvolutionPath:sourceSet.deconvolutionPath};
    // Manual browsing has already applied the selection; keep its other inputs.
    const next=preserveSelection && selectedPaths.has(assetPath(requestedAsset)) ? base : inputDataForAsset(base,requestedAsset);
    setSelectedSetName(next.assetSetName);onUpdate(next);
  },[requestedAsset,inputIntentPending,inputs.ready,dataSets,selectedProjectId,projectId,assetSetName,pepPaths,profilePath,transcriptomePath,deconvolutionPath,onUpdate]);

  // Auto-select first data set when detected
  useEffect(() => {
    if (!selectionExplicit && inputs.ready && !requestedAsset && !inputIntentPending && dataSets.length > 0 && autoSelectedProject.current !== selectedProjectId && pepPaths.length === 0 && !profilePath && !transcriptomePath && !deconvolutionPath) {
      const ds = assetSetName ? dataSets.find(set => set.name === assetSetName) : dataSets.length===1 ? dataSets[0] : undefined;
      if(!ds)return;
      autoSelectedProject.current = selectedProjectId;
      onUpdate({ projectId: selectedProjectId, assetSetName: ds.name, pepPaths: ds.pepPaths, profilePath: ds.profilePath, transcriptomePath: ds.transcriptomePath, deconvolutionPath: ds.deconvolutionPath });
      setSelectedSetName(ds.name);
    }
  }, [selectedProjectId, assetSetName, dataSets, pepPaths.length, profilePath, transcriptomePath, deconvolutionPath, onUpdate,requestedAsset,inputIntentPending,selectionExplicit,inputs.ready]);

  useEffect(() => {
    setSelectedProjectId(projectId);
  }, [projectId]);

  const applyDataSet = (name: string) => {
    setSelectionError("");
    pendingDataset.current=name;
    setSelectedSetName(name);
    setShowBrowser(false);
    onUpdate({projectId:selectedProjectId,assetSetName:name,pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""});
  };
  useEffect(()=>{
    if(!pendingDataset.current || !inputs.ready || pendingDataset.current!==inputs.scope || inputIntentPending)return;
    pendingDataset.current="";
    const ds=inputs.selected;
    onUpdate({projectId:selectedProjectId,assetSetName:ds.name,pepPaths:ds.pepPaths,profilePath:ds.profilePath,transcriptomePath:ds.transcriptomePath,deconvolutionPath:ds.deconvolutionPath});
  },[inputs.ready,inputs.scope,inputs.selected,inputIntentPending,selectedProjectId,onUpdate]);

  const removePepPath = (p: string) => {
    onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths: pepPaths.filter((x) => x !== p), profilePath, transcriptomePath, deconvolutionPath });
  };

  const handleBrowseSelect = (asset: ProjectAsset) => {
    if(asset.project_id!==selectedProjectId || !isInputAsset(asset)){setSelectionError("请选择当前项目的分析输入文件。");return;}
    if(!selectedSetName || getAssetSetName(asset)!==selectedSetName){setSelectionError("该文件不属于当前分析数据集，请先选择对应数据集。");return;}
    setSelectionError("");
    const select = (next:Stage1UpdateData)=>{setSelectedVersions(previous=>({...previous,[asset.id]:asset}));onUpdate(next,asset);};
    const path = assetPath(asset);
    const type = (asset.asset_type || "").toLowerCase();
    if (type.includes("profile") || type.includes("datapoint")) {
      select({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath: path, transcriptomePath, deconvolutionPath });
    } else if (type.includes("transcriptome") || type.includes("expression")) {
      select({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath: path, deconvolutionPath });
    } else if (["deconvolution", "cibersort"].includes(type)) {
      select({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath, deconvolutionPath: path });
    } else if (type === "pep") {
      if (!pepPaths.includes(path)) {
        select({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths: [...pepPaths, path], profilePath, transcriptomePath, deconvolutionPath });
      }
    }
  };

  const selectedAny = pepPaths.length > 0 || !!profilePath || !!transcriptomePath || !!deconvolutionPath;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      <div>
        <h2 style={{ margin: 0 }}>选择或上传数据</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          先选择项目，再选择本次分析所需的数据。已有数据可直接选用，不必填写服务器路径。
        </p>
      </div>

      {/* Project Selector */}
      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
          <ProjectPicker value={selectedProjectId}
            onChange={(id) => {
              setSelectedProjectId(id); setSelectedSetName(""); setShowBrowser(false); setShowUpload(false);
              autoSelectedProject.current = ""; pendingDataset.current = "";
              onUpdate({ projectId: id, assetSetName: "", pepPaths: [], profilePath: "", transcriptomePath: "", deconvolutionPath: "" });
            }} />
        </div>
        {projectDetail && (
          <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "var(--spacing-sm)" }}>
            {projectDetail.input_sample_count || 0} 个输入样本条目 · {inputs.datasets.reduce((total,dataset)=>total+dataset.input_count,0)} 个当前输入文件
          </p>
        )}
      </Card>

      {selectionError && <p role="alert" className="data-error">{selectionError}</p>}
      {assetSetName && !inputs.loading && !inputs.error && !inputs.containsScope(assetSetName) && !inputIntentPending && <p role="alert" className="data-error">指定数据集不存在或已移除，请选择其他数据集；不会自动替换输入。</p>}
      {inputs.error && <p role="alert" className="data-error">项目输入读取失败：{inputs.error}<button className="btn btn-secondary" onClick={inputs.refresh}>重新读取输入</button></p>}
      {/* Data Set selector */}
      {selectedProjectId && (
        <div style={{ background: "var(--bg-elevated)", borderRadius: "var(--radius-panel)", border: "1px solid var(--separator)", padding: "var(--spacing-lg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", marginBottom: "var(--spacing-md)" }}>
            <Layers size={16} style={{ color: "var(--text-secondary)" }} />
            <h4 style={{ margin: 0, fontSize: "0.9rem" }}>分析数据集</h4>
            {assetsLoading ? <Skeleton height="18px" width="60px" variant="text" /> : (
              <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", marginLeft: "auto" }}>
                {dataSets.length} 数据集 已找到
              </span>
            )}
          </div>

          {inputs.summaryLoading ? (
            <div style={{ display: "flex", gap: "var(--spacing-md)" }}>
              <Skeleton height="80px" width="180px" /><Skeleton height="80px" width="180px" />
            </div>
          ) : dataSets.length === 0 ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              尚无数据。点击下方“上传数据”，可单独上传 样本指标表 开始分析。
            </div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)", marginBottom: "var(--spacing-sm)" }}>
              {dataSets.map((ds) => (
                <button key={ds.name} onClick={() => applyDataSet(ds.name)} disabled={inputIntentPending} style={{
                  textAlign: "left", padding: "var(--spacing-md)", borderRadius: "var(--radius-control)",
                  cursor: "pointer", minWidth: "180px",
                  border: selectedSetName === ds.name ? "2px solid var(--accent)" : "1px solid var(--separator)",
                  background: selectedSetName === ds.name ? "rgba(0,113,227,0.06)" : "var(--bg-root)",
                  transition: "border-color var(--duration-fast)",
                }}>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "6px" }}>
                    {ds.name}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--text-secondary)" }}>
                    <span>克隆序列表： {inputs.datasets.find(dataset=>dataset.name===ds.name)?.kinds.pep?.count ?? ds.pepPaths.length} 个当前文件</span>
                    <span>样本指标表： {(inputs.datasets.find(dataset=>dataset.name===ds.name)?.kinds.profile?.count || ds.profilePath) ? "✓" : "—"}</span>
                    <span>转录组： {(inputs.datasets.find(dataset=>dataset.name===ds.name)?.kinds.transcriptome?.count || ds.transcriptomePath) ? "✓" : "—"}</span>
                    <span>免疫浸润： {(inputs.datasets.find(dataset=>dataset.name===ds.name)?.kinds.deconvolution?.count || ds.deconvolutionPath) ? "✓" : "—"}</span>
                  </div>
                  {selectedSetName === ds.name && <CheckCircle2 size={14} style={{ color: "var(--accent)", marginTop: "6px" }} />}
                </button>
              ))}
            </div>
          )}

          {assetsLoading && !inputs.summaryLoading && <p role="status">正在读取数据集 {inputs.scope} 的分析输入…</p>}
          {/* Manual override browser */}
          {selectedSetName && inputs.ready && (<>
            {inputIntentPending && <p role="status" style={{margin:0,color:"var(--text-secondary)",fontSize:"0.85rem"}}>正在核对所选文件，请稍候；筛选和已选版本会保留。</p>}
            <div aria-busy={inputIntentPending} inert={inputIntentPending || undefined} style={{opacity:inputIntentPending ? 0.65 : 1}}>
              <button onClick={() => setShowBrowser(!showBrowser)} style={{
                display: "inline-flex", alignItems: "center", gap: "4px", padding: "4px 0",
                border: "none", background: "transparent", color: "var(--text-secondary)",
                fontSize: "0.78rem", fontWeight: 500, cursor: "pointer",
              }}>
                {showBrowser ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <FolderTree size={14} />
                {showBrowser ? "收起文件浏览" : "浏览当前数据集文件"} （手动指定）
              </button>
              {showBrowser && (
                <div style={{ marginTop: "var(--spacing-sm)", border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", maxHeight: "300px", overflow: "auto" }}>
                  <DirectoryBrowser key={`${selectedProjectId}:${selectedSetName}`} projectId={selectedProjectId} assetSet={selectedSetName} inputsOnly onSelect={handleBrowseSelect} searchable />
                </div>
              )}
            </div>
          </>)}
        </div>
      )}

      {selectedProjectId && (
        <section>
          <button type="button" className="btn btn-primary" aria-expanded={showUpload} onClick={() => setShowUpload((open) => !open)}>
            {showUpload ? "收起上传" : "上传数据"}
          </button>
          {showUpload && <div style={{ marginTop: "var(--spacing-md)" }}>
            <AssetUpload key={selectedProjectId} projectId={selectedProjectId} initialAssetSet={selectedSetName} onSuccess={inputs.refresh} />
          </div>}
        </section>
      )}

      {selectedSetName && <section aria-label="选择输入版本" style={{display:"grid",gap:16}}>
        {([{key:"profilePath",title:"样本指标表",types:["profile","datapoint"],value:profilePath},
           {key:"transcriptomePath",title:"转录组",types:["transcriptome","expression"],value:transcriptomePath},
           {key:"deconvolutionPath",title:"免疫细胞浸润",types:["deconvolution","cibersort"],value:deconvolutionPath}] as const).map(field => {
          const candidates = (dataSets.find(set => set.name === selectedSetName)?.assets || []).filter(asset => (field.types as readonly string[]).includes(asset.asset_type));
          if (candidates.length < 2) return null;
          return <div key={field.key}><p>{field.title}有多份文件，请选择本次分析版本。</p><Select ariaLabel={`${field.title}版本`} value={field.value} options={candidates.map(asset => ({value:assetPath(asset), label:`${asset.original_name} · ${asset.uploaded_at?.replace("T"," ").slice(0,16) || asset.id}`}))}
            onChange={value => {const asset=candidates.find(candidate=>assetPath(candidate)===value);if(asset)setSelectedVersions(previous=>({...previous,[asset.id]:asset}));onUpdate({projectId:selectedProjectId, assetSetName:selectedSetName, pepPaths, profilePath, transcriptomePath, deconvolutionPath, [field.key]:value},asset);}} /></div>;
        })}
      </section>}
      {/* Baskets */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))", gap: "var(--spacing-lg)" }}>
        {/* PEP */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <Database size={18} style={{ color: "var(--accent)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>克隆序列表路径</span>
            </div>
            <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>{pepPaths.length} 路径</span>
          </div>
          {pepPaths.length === 0 ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              未选择 克隆序列表。仅做 样本指标表 箱线图时无需提供。
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              {pepPaths.slice(0,showAllClones?pepPaths.length:10).map((p, i) => (
                <div key={i} style={itemRow}>
                  <FileText size={14} style={{ flexShrink: 0, color: "var(--accent)" }} />
                  <span title={p} style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{selectedAssetByPath.get(p)?.original_name || p}{selectedAssetByPath.get(p)?.metadata?.superseded ? " · 历史版本" : ""}</span>
                  <button aria-label={`移除 ${selectedAssetByPath.get(p)?.original_name || p}`} onClick={() => removePepPath(p)} style={iconBtn} title="移除"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
                </div>
              ))}
              {pepPaths.length>10 && <button className="btn btn-secondary" aria-expanded={showAllClones} onClick={()=>setShowAllClones(value=>!value)}>{showAllClones?"收起克隆文件":`展开全部 ${pepPaths.length} 个已选克隆文件`}</button>}
            </div>
          )}
        </div>

        {/* Profile */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <BarChart3 size={18} style={{ color: "var(--success)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>样本指标表</span>
              {profilePath && <CheckCircle2 size={14} style={{ color: "var(--success)" }} />}
            </div>
          </div>
          {!profilePath ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              尚未选择 样本指标表。
            </div>
          ) : (
            <div style={itemRow}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{profilePath}</span>
              <button onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath: "", transcriptomePath, deconvolutionPath })} style={iconBtn} title="移除"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
            </div>
          )}
        </div>

        {/* Transcriptome */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <FileSpreadsheet size={18} style={{ color: "var(--warning)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>转录组</span>
              {transcriptomePath && <CheckCircle2 size={14} style={{ color: "var(--warning)" }} />}
            </div>
          </div>
          {!transcriptomePath ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              未识别到转录组数据。
            </div>
          ) : (
            <div style={itemRow}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{transcriptomePath}</span>
              <button onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath: "", deconvolutionPath })} style={iconBtn} title="移除"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
            </div>
          )}
        </div>
        {/* Deconvolution */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <FileSpreadsheet size={18} style={{ color: "var(--warning)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>免疫细胞浸润</span>
              {deconvolutionPath && <CheckCircle2 size={14} style={{ color: "var(--warning)" }} />}
            </div>
          </div>
          {!deconvolutionPath ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              未识别到免疫细胞浸润数据。
            </div>
          ) : (
            <div style={itemRow}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{deconvolutionPath}</span>
              <button onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath, deconvolutionPath: "" })} style={iconBtn} title="移除"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
            </div>
          )}
        </div>
      </div>

      {/* Confirm */}
      <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--spacing-md)", borderTop: "1px solid var(--separator)" }}>
        <button disabled={!selectedAny} onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath, deconvolutionPath })} style={{
          display: "inline-flex", alignItems: "center", gap: "var(--spacing-sm)", padding: "10px 24px",
          borderRadius: "var(--radius-control)", border: "none", fontWeight: 500, fontSize: "0.9rem",
          background: selectedAny ? "var(--success)" : "var(--bg-inset)",
          color: selectedAny ? "#fff" : "var(--text-tertiary)",
          cursor: selectedAny ? "pointer" : "not-allowed",
        }}>
          <CheckCircle2 size={16} /> 确认数据
        </button>
      </div>
    </div>
  );
}

/* ── Shared styles ── */

function tag(color: string): React.CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: "4px",
    padding: "3px 10px", borderRadius: "var(--radius-pill)",
    background: `color-mix(in srgb, var(--${color}) 12%, transparent)`,
    color: `var(--${color})`, fontSize: "0.72rem", fontWeight: 500,
  };
}

const basketStyle: React.CSSProperties = {
  background: "var(--bg-elevated)", borderRadius: "var(--radius-panel)",
  border: "1px solid var(--separator)", padding: "var(--spacing-md)",
  display: "flex", flexDirection: "column",
};

const basketHeaderStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  marginBottom: "var(--spacing-sm)",
};

const itemRow: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
  padding: "6px 10px", borderRadius: "var(--radius-control)",
  background: "var(--bg-root)", fontSize: "0.8rem",
};

const iconBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  width: "26px", height: "26px", borderRadius: "var(--radius-control)",
  border: "none", background: "transparent", cursor: "pointer", flexShrink: 0,
};
