import { InputFormatGuide } from "./InputFormatGuide";
import { useEffect, useMemo, useState, useRef } from "react";
import { Upload, FolderTree, FileText, Database, Plus, Tag, Trash2, Layers } from "lucide-react";
import { listProjectDatasets, uploadProjectAssets, registerProjectPath, previewUploadImpact, uploadImpactKey, isUploadImpactConflict } from "../../shared/api/projects";
import { Toggle } from "../../shared/components/Toggle";
import { FileDropZone } from "../../shared/components/FileDropZone";
import { PathInput } from "../../shared/components/PathInput";
import { Select } from "../../shared/components/Select";
import { useApi } from "../../shared/hooks/useApi";
import { nextAssetSetName } from "./assetSets";
import type { DatasetSummary, UploadImpactItem, UploadImpact } from "../../shared/api/projects";
import { createUploadOperationId, UploadResponseUnknownError } from "../../shared/api/uploadOperations";
import { UploadImpactPreview } from "./UploadImpactPreview";
import "./DataManagement.css";

/* ── Data Set builder — PEP(s) + Profile + Transcriptome as a group ─── */

type Props = {
  projectId: string;
  onSuccess: () => void;
  initialAssetSet?: string;
  initialAssetType?: string;
  onBusyChange?: (busy: boolean) => void;
  onPendingChange?: (count: number) => void;
  onScopeChange?: (datasets: string[]) => void;
};

interface SetEntry {
  groupLabel: string;
  pepPaths: string[];
  profileFile: { name: string; size: number; file: File } | null;
  transcriptomeFile: { name: string; size: number; file: File } | null;
  deconvolutionFile: { name: string; size: number; file: File } | null;
  pepFiles: File[];
}

const emptySet = (): SetEntry => ({
  groupLabel: "Set1",
  pepPaths: [],
  profileFile: null,
  transcriptomeFile: null,
  deconvolutionFile: null,
  pepFiles: [],
});

const setFromExisting = (set?: DatasetSummary, fallbackName = "Set1"): SetEntry => ({
  ...emptySet(), groupLabel: set?.name || fallbackName,
});

export function AssetUpload({ projectId, onSuccess, initialAssetSet = "", initialAssetType = "", onBusyChange, onPendingChange, onScopeChange }: Props) {
  const [inputType, setInputType] = useState(initialAssetType);
  const [sets, setSets] = useState<SetEntry[]>([emptySet()]);
  const [mode, setMode] = useState<"existing" | "new">(initialAssetSet ? "existing" : "new");
  const [selectedSetName, setSelectedSetName] = useState(initialAssetSet);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const [pepDrafts, setPepDrafts] = useState<Record<number, string>>({});
  const [pendingLabel, setPendingLabel] = useState("放弃本次选择并切换");
  const [pendingMessage, setPendingMessage] = useState("切换后会放弃本次未保存的文件和目录选择。");
  const [pendingChange, setPendingChange] = useState<(() => void) | null>(null);
  function changeContext(action: () => void) {
    if (sets.some(hasPendingAsset) || Object.values(pepDrafts).some(value => value.trim())) {
      setPendingLabel("放弃本次选择并切换");
      setPendingMessage("切换后会放弃本次未保存的文件和目录选择。");
      setPendingChange(() => action);
    } else action();
  }
  const [uploadRows, setUploadRows] = useState<{ key: string; name: string; stage: string; progress?: number; error?: string }[]>([]);
  const controller = useRef<AbortController | null>(null);
  const fileOperations = useRef(new WeakMap<File, Map<string, string>>());
  const pathOperations = useRef(new Map<string, string>());
  function operation(file: File | null, scope: string) {
    let operations = pathOperations.current;
    if (file) {
      operations = fileOperations.current.get(file) || new Map<string, string>();
      fileOperations.current.set(file, operations);
    }
    // A pending selection keeps its identity even if options change after a disconnect.
    const identity = file ? "file" : String(JSON.parse(scope)[1]);
    const previous = operations.get(identity);
    const operationId = previous || createUploadOperationId();
    operations.set(identity, operationId);
    return { operationId, retry: !!previous };
  }
  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => { onBusyChange?.(state === "loading"); }, [state, onBusyChange]);

  const datasetsState = useApi(() => listProjectDatasets(projectId), [projectId, message]);
  const existingSets = useMemo(() => datasetsState.status === "ready" ? datasetsState.data.datasets : [], [datasetsState]);
  const defaultNewSetName = useMemo(() => nextAssetSetName(existingSets), [existingSets]);
  const newNameInitialized = useRef(false);
  const [confirmedExistingNames,setConfirmedExistingNames] = useState<string[]>([]);
  const createdByThisDraft = useRef(new Set<string>());
  const selectedExistingSet = existingSets.find(set => set.name === selectedSetName);

  useEffect(() => {
    if (mode === "existing" && !selectedSetName && existingSets.length > 0) {
      setSelectedSetName(existingSets[0].name);
    }
  }, [existingSets, mode, selectedSetName]);

  useEffect(() => {
    if (mode !== "existing") return;
    const name = selectedSetName || existingSets[0]?.name || "Set1";
    setSets(previous => {
      const refreshed = setFromExisting(selectedExistingSet, name);
      const selected = previous.length === 1 && previous[0].groupLabel === name ? previous[0] : null;
      return [selected ? { ...refreshed, pepPaths: selected.pepPaths, pepFiles: selected.pepFiles,
        profileFile: selected.profileFile, transcriptomeFile: selected.transcriptomeFile,
        deconvolutionFile: selected.deconvolutionFile } : refreshed];
    });
  }, [
    mode,
    selectedSetName,
    selectedExistingSet?.name,
    existingSets.length,
  ]);

  useEffect(() => {
    if (mode !== "new" || datasetsState.status !== "ready" || newNameInitialized.current) return;
    newNameInitialized.current = true;
    setSets(previous => previous.map((set, index) => index === 0 && !hasPendingAsset(set) ? { ...set, groupLabel: defaultNewSetName } : set));
  }, [defaultNewSetName, datasetsState.status, mode]);

  const updateSet = (idx: number, patch: Partial<SetEntry>) => {
    if ("groupLabel" in patch) newNameInitialized.current = true;
    setSets((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  const addSet = () => setSets((prev) => [...prev, { ...emptySet(), groupLabel: `Set${existingSets.length + prev.length + 1}` }]);
  const removeSet = (idx: number) => {
    if (sets.length <= 1) return;
    const remove = () => {
      setSets(previous => previous.filter((_, index) => index !== idx));
      setPepDrafts(previous => Object.fromEntries(Object.entries(previous).filter(([key]) => Number(key) !== idx)
        .map(([key, value]) => [Number(key) > idx ? Number(key) - 1 : Number(key), value])));
    };
    if (hasPendingAsset(sets[idx]) || pepDrafts[idx]?.trim()) {
      setPendingLabel("放弃选择并移除数据集");
      setPendingMessage(`将移除“${sets[idx].groupLabel}”的未保存选择；其他数据集的草稿会保留。`);
      setPendingChange(() => remove);
    } else remove();
  };

  const updatePepDraft = (idx: number, value: string) => {
    setPepDrafts((prev) => ({ ...prev, [idx]: value }));
  };

  const addPepPath = (idx: number, rawPath: string) => {
    const path = rawPath.trim();
    if (!path) return;
    const target = sets[idx];
    if (!target || target.pepPaths.includes(path)) {
      setPepDrafts((prev) => ({ ...prev, [idx]: "" }));
      return;
    }
    pathOperations.current.delete(path);
    updateSet(idx, { pepPaths: [...target.pepPaths, path] });
    setPepDrafts((prev) => ({ ...prev, [idx]: "" }));
  };

  const publishingImpacts = useRef<UploadImpact[]>([]);
  const [impactConflict, setImpactConflict] = useState(false);
  const [impactRevision, setImpactRevision] = useState(0);
  const pending = sets.flatMap((set, index) => {
    const dataset = (mode === "existing" ? selectedSetName : set.groupLabel).trim() || `Set${index + 1}`;
    const files = [
      ...set.pepFiles.map(file => ({ file, assetType:"pep", directory:false, type: "克隆序列表", remove: () => updateSet(index, { pepFiles: set.pepFiles.filter(item => item !== file) }) })),
      ...([ ["profileFile", "样本指标表", "profile"], ["transcriptomeFile", "转录组", "transcriptome"], ["deconvolutionFile", "免疫细胞浸润", "deconvolution"] ] as const).flatMap(([key, type, assetType]) =>
        set[key] ? [{ file: set[key]!.file, type, assetType, directory:false, remove: () => updateSet(index, { [key]: null }) }] : []),
    ];
    return [ ...files.map(item => ({ ...item, dataset, name: item.file.name, size: item.file.size })),
      ...set.pepPaths.map(path => ({ dataset, name: path, assetType:"pep", directory:true, type: "克隆目录", size: 0,
        remove: () => updateSet(index, { pepPaths: set.pepPaths.filter(item => item !== path) }) })) ];
  });
  const impactItems: UploadImpactItem[] = pending.map(item => ({
    asset_type: item.assetType, asset_set: item.dataset, name: item.name.trim(), directory: !!item.directory,
  }));
  const impactScope = JSON.stringify([projectId, impactItems]);
  const impactState = useApi(async () => ({scope: impactScope,
    ...(await previewUploadImpact(projectId, impactItems))}),
    [projectId, impactScope, impactRevision, message], replaceExisting && pending.length > 0 && state !== "loading" && !impactConflict);
  const impactReady = impactState.status === "ready" && impactState.data.scope === impactScope;
  const impactMap = new Map(impactReady ? impactState.data.impacts.map(item => [uploadImpactKey(item), item]) : []);
  const targets = impactItems.filter(item => !item.directory).map(item => JSON.stringify([
    item.asset_set, item.asset_type, item.asset_type === "pep" ? item.name : "",
  ]));
  const duplicateUpdate = replaceExisting && new Set(targets).size !== targets.length;
  const existingNameCollisions = mode === "new" ? [...new Set(pending.map(item=>item.dataset).filter(name=>!createdByThisDraft.current.has(name) && existingSets.some(set=>set.name===name)))] : [];
  const collisionConfirmed = existingNameCollisions.every(name=>confirmedExistingNames.includes(name));
  const canSubmit = pending.length > 0 && datasetsState.status === "ready" && (mode === "new" || !!selectedSetName) && collisionConfirmed
    && !duplicateUpdate && (!replaceExisting || (!impactConflict && impactReady && impactItems.every(item=>impactMap.has(uploadImpactKey(item)))));
  function recheckImpact() { setImpactConflict(false); setImpactRevision(previous => previous + 1); }

  const handleUpload = async () => {
    if (state === 'loading' || !canSubmit) return;
    const validSets = sets.map((set, index) => ({ set, index })).filter(({set}) => hasPendingAsset(set));
    if (!validSets.length) return;
    publishingImpacts.current = impactReady ? impactState.data.impacts : [];
    const aborter = new AbortController(); controller.current = aborter;
    setState('loading'); setMessage(''); setUploadRows([]);
    let uploaded = 0; const errors: string[] = [];
    const row = (key: string, patch: { name?: string; stage?: string; progress?: number; error?: string }) =>
      setUploadRows(previous => previous.some(item => item.key === key)
        ? previous.map(item => item.key === key ? { ...item, ...patch } : item)
        : [...previous, { key, name: patch.name || key, stage: patch.stage || '等待上传', ...patch }]);
    for (const {set: s, index} of validSets) {
      const label = (mode === 'existing' ? selectedSetName : s.groupLabel).trim() || `Set${index + 1}`;
      for (const pepPath of s.pepPaths) {
        if (aborter.signal.aborted) break;
        const key = `${index}:path:${pepPath}`;
        row(key, { name: pepPath, stage: '正在登记' });
        try {
          await registerProjectPath(projectId, { storagePath: pepPath.trim(), assetSet: label, signal: aborter.signal,
            ...operation(null, JSON.stringify([label, pepPath.trim()])),
            onStatusCheck: () => row(key, { stage: '正在核对保存结果', progress: undefined }) });
          if(mode==='new')createdByThisDraft.current.add(label);
          uploaded++; row(key, { stage: '已登记，待分析检查' });
          setSets(previous => previous.map((set, position) => position === index ? { ...set, pepPaths: set.pepPaths.filter(path => path !== pepPath) } : set));
        } catch (reason) { const error = reason instanceof Error ? reason.message : '目录登记失败'; errors.push(error); row(key, { stage: reason instanceof UploadResponseUnknownError ? '保存状态待确认' : '未登记', error }); }
      }
      const entries = [
        ...s.pepFiles.map(file => ({ type: 'pep', file, key: '' })),
        ...(s.profileFile ? [{ type: 'profile', file: s.profileFile.file, key: 'profileFile' }] : []),
        ...(s.transcriptomeFile ? [{ type: 'transcriptome', file: s.transcriptomeFile.file, key: 'transcriptomeFile' }] : []),
        ...(s.deconvolutionFile ? [{ type: 'deconvolution', file: s.deconvolutionFile.file, key: 'deconvolutionFile' }] : []),
      ];
      for (const [position, entry] of entries.entries()) {
        const key = `${index}:${entry.type}:${position}:${entry.file.name}`;
        if (aborter.signal.aborted) { row(key, { name: entry.file.name, stage: '未开始，已保留选择' }); continue; }
        row(key, { name: `${label} · ${entry.file.name}`, stage: '正在上传', progress: 0 });
        try {
          const result = await uploadProjectAssets(projectId, { assetType: entry.type, files: [entry.file], replaceExisting,
            assetSet: label, signal: aborter.signal,
            expectedVersions: replaceExisting ? impactMap.get(uploadImpactKey({asset_type:entry.type,asset_set:label,name:entry.file.name,directory:false}))?.expected_versions : undefined,
            ...operation(entry.file, JSON.stringify([label, entry.type, replaceExisting])),
            onStatusCheck: () => row(key, { stage: '正在核对保存结果', progress: undefined }), onProgress: progress => row(key, { progress,
              stage: progress === 100 ? '已传输，正在保存与检查' : '正在上传' }) });
          if(mode==='new' && result.assets.length)createdByThisDraft.current.add(label);
          uploaded += result.assets.length;
          const validation = (result.assets[0]?.metadata as any)?.validation;
          row(key, { stage: validation?.status === 'valid' ? '已保存，校验通过' : validation?.status === 'failed' ? '已保存，校验需重试' : '已保存，查看校验状态', progress: undefined });
          setSets(previous => previous.map((set, setIndex) => setIndex !== index ? set : entry.type === 'pep'
            ? { ...set, pepFiles: set.pepFiles.filter(file => file !== entry.file) }
            : { ...set, [entry.key]: null }));
        } catch (reason) {
          const conflict = isUploadImpactConflict(reason);
          if (conflict) setImpactConflict(true);
          const error = reason instanceof Error ? reason.message : '上传失败'; errors.push(`${entry.file.name}：${error}`);
          row(key, { stage: conflict ? '版本已变化，需重新核对' : reason instanceof UploadResponseUnknownError ? '保存状态待确认' : aborter.signal.aborted ? '已取消' : '上传失败', error });
        }
      }
    }
    controller.current = null;
    setState(errors.length || aborter.signal.aborted ? 'error' : 'idle');
    setMessage(`已保存 ${uploaded} 个文件${errors.length ? `；${errors.length} 个文件尚未完成确认，详情见逐文件结果。成功项已移出选择，重试前会核对剩余文件的保存结果。` : aborter.signal.aborted ? '；已取消后续上传，未保存的选择已保留。' : '，可以继续检查数据。'}`);
    if (uploaded > 0) onSuccess();
  };

  const scope = JSON.stringify([...new Set(sets.map((set, index) =>
    (mode === "existing" ? selectedSetName : set.groupLabel).trim() || `Set${index + 1}`))]);
  useEffect(() => { onScopeChange?.(JSON.parse(scope) as string[]); }, [scope, onScopeChange]);
  const pendingSize = pending.reduce((sum, item) => sum + item.size, 0);
  const draftCount = pending.length + Object.values(pepDrafts).filter(value => value.trim()).length;
  const rangeReady = datasetsState.status === "ready" && (mode === "existing" ? !!selectedSetName : sets.every(set => !!set.groupLabel.trim()));
  const importStep = !rangeReady ? 0 : !pending.length ? 1 : 2;
  useEffect(() => { onPendingChange?.(draftCount); }, [draftCount, onPendingChange]);
  useEffect(() => {
    if (!draftCount && state !== "loading") return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draftCount, state]);

  return (
    <div className="data-upload-builder">
      <div className="data-upload-fields">
      <ol className="data-import-steps" aria-label="导入步骤">{["选择数据集", "选择文件", "确认与保存"].map((label, index) => <li key={label} aria-current={index === importStep ? "step" : undefined} data-complete={index < importStep}>{label}</li>)}</ol>
      {datasetsState.status === "error" && <p className="data-error" role="alert">数据集摘要读取失败，已选文件会保留。<button className="btn btn-secondary" onClick={datasetsState.refetch}>重新读取数据集</button></p>}
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h4 style={{ margin: 0, fontSize: "0.95rem" }}>上传分析数据</h4>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            可单独上传 样本指标表 开始箱线图分析；克隆序列表 和表达矩阵按分析需要补充。文件将上传至服务器。
          </p>
        </div>
        <StatusBadge status={state === "loading" ? "running" : state === "error" ? "failed" : "idle"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(260px, 100%), 1fr))", gap: "var(--spacing-md)", alignItems: "end" }}>
        <label className="field-label">
          导入到哪里
          <Select
            value={mode}
            onChange={(value) => {
              const nextMode = value as "existing" | "new";
              if (nextMode === mode) return;
              changeContext(() => {
              setMode(nextMode);
              setPepDrafts({});
              if (nextMode === "new") {
                newNameInitialized.current = true;
                setSets([{ ...emptySet(), groupLabel: defaultNewSetName }]);
              } else {
                const nextName = selectedSetName || existingSets[0]?.name || "";
                setSelectedSetName(nextName);
                setSets([setFromExisting(undefined, nextName || "Set1")]);
              }
              });
            }}
            disabled={state === "loading"}
            options={[
              { value: "new", label: "新建数据集" },
              { value: "existing", label: "添加到已有数据集" },
            ]}
          />
        </label>
        {mode === "existing" ? (
          <label className="field-label">
            已有数据集
            <Select
              value={selectedSetName}
              onChange={(name) => {
                if (name === selectedSetName) return;
                changeContext(() => {
                  setSelectedSetName(name);
                  setPepDrafts({});
                  setSets([setFromExisting(undefined, name || "Set1")]);
                });
              }}
              disabled={state === "loading" || existingSets.length === 0}
              placeholder={existingSets.length === 0 ? "暂无数据集" : "选择数据集"}
              options={existingSets.map((set) => ({
                value: set.name,
                label: `${set.display_name || set.name}${set.archived ? " · 已归档" : ""} · ${set.input_count} 个文件`,
              }))}
            />
          </label>
        ) : (
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", paddingBottom: "10px" }}>
            新数据集默认命名为 {defaultNewSetName}；可在数据集卡片中修改名称。
          </div>
        )}
      </div>

      <p className="data-muted">添加文件会保留已有输入。需要替换时，请在底部选择“更新当前版本”，并核对受影响文件。</p>
      <label className="field-label">准备上传的输入类型<Select value={inputType} ariaLabel="准备上传的输入类型" disabled={state === "loading"}
        onChange={setInputType} options={[{value:"", label:"多种输入"}, {value:"pep",label:"克隆序列表"}, {value:"profile",label:"样本指标表"}, {value:"transcriptome",label:"转录组"}, {value:"deconvolution",label:"免疫细胞浸润"}]} /></label>
      <InputFormatGuide kind={inputType}/>
      {sets.map((s, idx) => (
        <div key={idx} style={{
          background: "var(--bg-root)", borderRadius: "var(--radius-panel)", border: "1px solid var(--separator)",
          padding: "var(--spacing-lg)", display: "flex", flexDirection: "column", gap: "var(--spacing-md)",
        }}>
          {/* Set header */}
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <Layers size={16} style={{ color: "var(--accent)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>
                {mode === "existing" ? `当前数据集： ${selectedSetName || s.groupLabel}` : `数据集 ${idx + 1}`}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)" }}>
              {/* Group label */}
              <div style={{ display: "flex", alignItems: "center", gap: "4px", background: "var(--bg-elevated)", borderRadius: "var(--radius-pill)", border: "1px solid var(--separator)", padding: "3px 10px" }}>
                <Tag size={12} style={{ color: "var(--text-tertiary)" }} />
                <input
                  value={mode === "existing" ? selectedSetName : s.groupLabel}
                  onChange={(e) => updateSet(idx, { groupLabel: e.target.value })}
                  aria-label={`数据集 ${idx+1} 名称`} className="data-upload-dataset-name" placeholder="数据集名称"
                  disabled={state === "loading" || mode === "existing"}
                  style={{ fontSize: "0.82rem", width: "min(240px, 100%)", fontFamily: "var(--font-family)" }}
                />
              </div>
              {sets.length > 1 && (
                <button type="button" onClick={() => removeSet(idx)} className="data-path-remove" aria-label={'移除数据集 '+s.groupLabel} title="移除数据集" disabled={state === "loading"}>
                  <Trash2 size={14} style={{ color: "var(--danger)" }} />
                </button>
              )}
            </div>
          </div>

          {/* PEP Paths */}
          <div hidden={!!inputType && inputType !== "pep"}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <FolderTree size={14} style={{ color: "var(--accent)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>克隆序列表</span>
              <span className="data-input-requirement">（组库分析需要，可多选）</span>
            </div>
            {mode === "existing" && (
              <ExistingInputSummary projectId={projectId} dataset={selectedSetName} kind="pep" label="克隆序列表"
                summary={selectedExistingSet} ready={datasetsState.status === "ready"} />
            )}
            <FileDropZone
              files={s.pepFiles.map(file => ({ name: file.name, size: file.size, file }))}
              onFilesAdded={incoming => updateSet(idx, { pepFiles: [...s.pepFiles, ...Array.from(incoming as FileList)] })}
              onRemoveFile={name => updateSet(idx, { pepFiles: s.pepFiles.filter(file => file.name !== name) })}
              accept=".csv,.tsv,.csv.gz" multiple disabled={state === "loading"}
              label="上传克隆序列表，可选择多个文件" />
            <details><summary style={{ cursor: "pointer", margin: "10px 0" }}>从服务器已有目录导入</summary>
            <div className="data-directory-input">
              <PathInput
                value={pepDrafts[idx] || ""}
                onChange={(path) => updatePepDraft(idx, path)}
                onCommit={(path) => addPepPath(idx, path)}
                placeholder="/data/projects/.../pep_sample_dir/"
                disabled={state === "loading"}
                browsable
                hint="浏览或输入服务器目录，按回车或点击“添加”登记路径。"
              />
              <button
                type="button"
                onClick={() => addPepPath(idx, pepDrafts[idx] || "")}
                disabled={state === "loading" || !(pepDrafts[idx] || "").trim()}
                className="btn btn-secondary"
                style={{ minHeight: "42px", padding: "8px 14px", whiteSpace: "nowrap" }}
              >
                <Plus size={14} />
                添加
              </button>
            </div>
            {s.pepPaths.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xs)", marginTop: "var(--spacing-sm)" }}>
                {mode === "existing" && <span className="data-muted">待添加的克隆序列表</span>}
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
                {s.pepPaths.map((p, pi) => (
                  <span key={pi} style={{
                    display: "inline-flex", alignItems: "center", gap: "4px",
                    padding: "3px 10px", borderRadius: "var(--radius-pill)",
                    background: "color-mix(in srgb, var(--accent) 10%, transparent)",
                    color: "var(--accent)", fontSize: "0.75rem", border: "1px solid color-mix(in srgb, var(--accent) 20%, transparent)",
                  }}>
                    <span style={{ maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p}>{p}</span>
                    <button type="button" className="data-path-remove" aria-label={'移除目录 '+p} title={'移除目录 '+p} disabled={state === "loading"} onClick={() => updateSet(idx, { pepPaths: s.pepPaths.filter((_, i) => i !== pi) })}>
                      <Trash2 size={15} aria-hidden="true" />
                    </button>
                  </span>
                ))}
                </div>
              </div>
            )}
            </details>
          </div>

          {/* Profile */}
          <div hidden={!!inputType && inputType !== "profile"}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <FileText size={14} style={{ color: "var(--success)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>样本指标表</span>
              <span className="data-input-requirement">（按分析需要）</span>
            </div>
            {mode === "existing" && (
              <ExistingInputSummary projectId={projectId} dataset={selectedSetName} kind="profile" label="样本指标表"
                summary={selectedExistingSet} ready={datasetsState.status === "ready"} />
            )}
            <FileDropZone
              files={s.profileFile ? [{ name: s.profileFile.name, size: s.profileFile.size, file: s.profileFile.file }] : []}
              onFilesAdded={(incoming) => {
                const f = Array.from(incoming as FileList)[0];
                if (f) updateSet(idx, { profileFile: { name: f.name, size: f.size, file: f } });
              }}
              onRemoveFile={() => updateSet(idx, { profileFile: null })}
              accept=".csv,.tsv,.csv.gz,.xlsx"
              multiple={false}
              disabled={state === "loading"}
              label={mode === "existing" && selectedExistingSet?.kinds.profile?.count ? "选择新的样本指标表" : "上传样本指标表（逗号分隔、制表符分隔或表格文件）"}
            />
          </div>

          {/* Transcriptome */}
          <div hidden={!!inputType && inputType !== "transcriptome"}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <Database size={14} style={{ color: "var(--warning)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>转录组</span>
              <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>（可选）</span>
            </div>
            {mode === "existing" && (
              <ExistingInputSummary projectId={projectId} dataset={selectedSetName} kind="transcriptome" label="转录组"
                summary={selectedExistingSet} ready={datasetsState.status === "ready"} />
            )}
            <FileDropZone
              files={s.transcriptomeFile ? [{ name: s.transcriptomeFile.name, size: s.transcriptomeFile.size, file: s.transcriptomeFile.file }] : []}
              onFilesAdded={(incoming) => {
                const f = Array.from(incoming as FileList)[0];
                if (f) updateSet(idx, { transcriptomeFile: { name: f.name, size: f.size, file: f } });
              }}
              onRemoveFile={() => updateSet(idx, { transcriptomeFile: null })}
              accept=".csv,.tsv,.csv.gz,.xlsx"
              multiple={false}
              disabled={state === "loading"}
              label={mode === "existing" && selectedExistingSet?.kinds.transcriptome?.count ? "将表达矩阵拖到此处以添加或替换" : "将表达矩阵拖到此处（可选）"}
            />
          </div>
          {/* Deconvolution */}
          <div hidden={!!inputType && inputType !== "deconvolution"}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <Database size={14} style={{ color: "var(--warning)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>免疫细胞浸润</span>
              <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>（可选）</span>
            </div>
            {mode === "existing" && (
              <ExistingInputSummary projectId={projectId} dataset={selectedSetName} kind="deconvolution" label="免疫细胞浸润"
                summary={selectedExistingSet} ready={datasetsState.status === "ready"} />
            )}
            <FileDropZone
              files={s.deconvolutionFile ? [{ name: s.deconvolutionFile.name, size: s.deconvolutionFile.size, file: s.deconvolutionFile.file }] : []}
              onFilesAdded={(incoming) => {
                const f = Array.from(incoming as FileList)[0];
                if (f) updateSet(idx, { deconvolutionFile: { name: f.name, size: f.size, file: f } });
              }}
              onRemoveFile={() => updateSet(idx, { deconvolutionFile: null })}
              accept=".csv,.tsv,.csv.gz,.xlsx"
              multiple={false}
              disabled={state === "loading"}
              label={mode === "existing" && selectedExistingSet?.kinds.deconvolution?.count ? "将浸润结果表拖到此处以添加或替换" : "将浸润结果表拖到此处（可选）"}
            />
          </div>
        </div>
      ))}

      {pending.length > 0 && <section className="data-upload-queue" aria-label="本次提交清单">
        <div className="data-section-header"><h4>本次提交 · {pending.length} 项</h4><span className="data-muted">文件合计 {(pendingSize / 1024 / 1024).toFixed(2)} 兆字节</span></div>
        <p className="data-muted">切换输入类型不会移除已选项。保存时将提交以下全部文件和目录。</p>
        <ul>{pending.map((item, index) => <li key={`${item.dataset}:${item.type}:${index}`}><div><strong>{item.name}</strong><small>{item.dataset} · {item.type} · {item.directory?"新增目录登记":replaceExisting ? "核对更新范围" : "添加新输入"}</small></div>
          <button className="btn btn-secondary" disabled={state === "loading"} onClick={item.remove} aria-label={`从提交清单移除 ${item.name}`}>移除</button></li>)}</ul>
      </section>}
      {pending.length>0 && <UploadImpactPreview projectId={projectId} pending={impactItems}
        impacts={state === "loading" ? publishingImpacts.current : impactReady ? impactState.data.impacts : []} replaceExisting={replaceExisting}
        loading={state !== "loading" && replaceExisting && !impactConflict && !impactReady && impactState.status!=="error"}
        error={impactState.status==="error" ? impactState.error : ""} conflict={impactConflict}
        onConflict={()=>setImpactConflict(true)} onRetry={recheckImpact} busy={state === "loading"}/>}
      {existingNameCollisions.length>0 && <section className="data-draft-warning"><p>名称已存在：{existingNameCollisions.join("、")}。保存会将文件添加到已有数据集；如需独立数据集，请修改名称。</p><label><input type="checkbox" checked={collisionConfirmed} disabled={state==="loading"} onChange={event=>setConfirmedExistingNames(event.target.checked?existingNameCollisions:[])}/>确认使用这些已有数据集</label></section>}
      {duplicateUpdate && <p role="alert" className="data-error">同一数据集存在重复更新目标，请移除同名克隆或重复的表格类型后保存。</p>}
      {/* Add set button */}
      {mode === "new" && <button onClick={addSet} disabled={state === "loading"} style={{
        display: "inline-flex", alignItems: "center", gap: "var(--spacing-sm)", padding: "8px 16px",
        borderRadius: "var(--radius-control)", border: "1px dashed var(--separator)", background: "transparent",
        color: "var(--text-secondary)", fontSize: "0.82rem", fontWeight: 500, cursor: "pointer", alignSelf: "flex-start",
      }}>
        <Plus size={15} /> 添加数据集
      </button>}

      {pendingChange && <section className="data-draft-warning" role="alert">
        <p>{pendingMessage}</p>
        <div className="data-row-actions"><button className="btn btn-primary" onClick={() => setPendingChange(null)}>继续编辑</button>
          <button className="btn btn-danger" onClick={() => { pendingChange(); setPendingChange(null); }}>{pendingLabel}</button></div>
      </section>}
      {uploadRows.length > 0 && <div className="data-upload-progress" aria-live="polite"><ul>{uploadRows.map(item => <li key={item.key}><span>{item.name}</span><span>{item.stage}{typeof item.progress === 'number' ? ` · ${item.progress}%` : ''}{item.error ? `：${item.error}` : ''}</span></li>)}</ul></div>}
      {message && (
        <div style={{ padding: "var(--spacing-md) var(--spacing-lg)", borderRadius: "var(--radius-control)", background: state === "error" ? "rgba(255,59,48,0.08)" : "rgba(52,199,89,0.08)", border: `1px solid ${state === "error" ? "var(--danger)" : "var(--success)"}`, color: state === "error" ? "var(--danger)" : "var(--success)", fontSize: "0.85rem", fontWeight: 500 }}>{message}</div>
      )}
      </div>
      {/* Submit */}
      <div className="data-upload-actions" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--separator)", paddingTop: "var(--spacing-md)" }}>
        <Toggle checked={replaceExisting} onChange={setReplaceExisting} disabled={state === "loading"} label="更新当前版本（保留历史文件；克隆文件按同名更新）" size="sm" />
        <button disabled={!canSubmit || state === "loading" || !!pendingChange} onClick={handleUpload} className="btn btn-primary" style={{ padding: "10px 24px" }}>
          <Upload size={15} />
          {state === "loading" ? "正在上传…" : `保存数据（${pending.length} 项）`}
        </button>
        {state === "loading" && <button className="btn btn-secondary" onClick={() => controller.current?.abort()}>取消剩余上传</button>}
        <p className="data-upload-action-status" role="status">{state === "loading" ? `已完成 ${uploadRows.filter(item=>item.stage.startsWith("已保存") || item.stage.startsWith("已登记")).length} 项 · 未保存选择会保留` : datasetsState.status!=="ready" ? "读取数据集范围后可以保存；已选文件会保留。" : !collisionConfirmed ? "请修改名称，或确认添加到已有数据集。" : impactConflict ? "当前版本已变化，请重新核对更新范围。" : duplicateUpdate ? "请先处理重复更新目标。" : replaceExisting && pending.length && !impactReady ? "完成更新范围核对后可以保存。" : !pending.length ? "选择文件或添加目录后可以保存。" : `准备保存 ${pending.length} 项 · 四类输入按分析需要提供`}</p>
      </div>


    </div>
  );
}

function hasPendingAsset(set: SetEntry): boolean {
  return set.pepPaths.length > 0 || Boolean(set.profileFile || set.transcriptomeFile || set.deconvolutionFile || set.pepFiles.length);
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    idle: { bg: "var(--bg-inset)", text: "var(--text-tertiary)", label: "就绪" },
    running: { bg: "rgba(0,113,227,0.1)", text: "var(--accent)", label: "处理中" },
    failed: { bg: "rgba(255,59,48,0.1)", text: "var(--danger)", label: "错误" },
  };
  const s = map[status] || map.idle;
  return <span style={{ padding: "3px 10px", borderRadius: "var(--radius-pill)", fontSize: "0.72rem", fontWeight: 600, background: s.bg, color: s.text }}>{s.label}</span>;
}

function ExistingInputSummary({projectId,dataset,kind,label,summary,ready}:{
  projectId:string;dataset:string;kind:string;label:string;summary?:DatasetSummary;ready:boolean;
}) {
  const count = summary?.kinds[kind]?.count || 0;
  const link = `/management/projects/${encodeURIComponent(projectId)}?${new URLSearchParams({tab:"assets",asset_set:dataset,file_type:kind})}`;
  return <div className="data-existing-input-summary"><span>{!ready ? "正在读取输入概况…" : count ? `已登记 ${count} 个${label}文件` : `此数据集尚未提供${label}。`}</span>
    {ready && count>0 && <a href={link}>查看文件与版本</a>}</div>;
}
