import { useState, useCallback, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  FlaskConical,
} from "lucide-react";
import { PageHeader } from "../../shared/components/PageHeader";
import { Stepper } from "../../shared/components/Stepper";
import type { StepDef } from "../../shared/components/Stepper";
import { useApi } from "../../shared/hooks/useApi";
import { inspectScriptHubDataSelection, listScriptHubModules, readScriptHubTablePreview } from "../../shared/api/scriptHub";
import type { ScriptHubPepPreview } from "../../shared/api/scriptHub";
import { StageIndicator } from "../../features/scripthub/StageIndicator";
import { Stage1DataIntake } from "../../features/scripthub/stages/Stage1DataIntake";
import { Stage2SourceInspection } from "../../features/scripthub/stages/Stage2SourceInspection";
import { Stage3ModuleConfig } from "../../features/scripthub/stages/Stage3ModuleConfig";
import { Stage4Execution } from "../../features/scripthub/stages/Stage4Execution";
import { Stage6History } from "../../features/scripthub/stages/Stage6History";
import { Stage5Results } from "../../features/scripthub/stages/Stage5Results";
import type { InspectionResult } from "../../features/scripthub/stages/Stage2SourceInspection";
import type { TablePreview } from "../../features/scripthub/stages/Stage2SourceInspection";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { hasAnySelectableModule, isModuleSelectable } from "../../features/scripthub/moduleRequirements";

import type { AnalysisTool } from "../../features/analysis/tools";
import { useAnalysisData } from "../../features/analysis/AnalysisDataContext";

/* ── Wizard State ── */
interface WizardState {
  stage: number; // 1-5
  projectId: string;
  assetSetName: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  deconvolutionPath?: string;
  inspection: InspectionResult | null;
  selectedModules: string[];
  moduleConfigs: Record<string, Record<string, unknown>>;
  jobIds: string[];
  resultsByJobId: Record<string, JobResultsResponse>;
}

const INITIAL_STATE: WizardState = {
  stage: 1,
  projectId: "",
  assetSetName: "",
  pepPaths: [],
  profilePath: "",
  transcriptomePath: "",
  deconvolutionPath: "",
  inspection: null,
  selectedModules: [],
  moduleConfigs: {},
  jobIds: [],
  resultsByJobId: {},
};

const WIZARD_STEPS = [
  "上传与选择数据",
  "检查数据",
  "选择分析与分组",
  "运行分析",
  "查看结果",
];

export function ScriptHubWizard({tool}:{tool?:AnalysisTool} = {}) {
  const {data:sharedData,setData:shareData}=useAnalysisData();
  const fixedModule=tool?.module;
  const initialModules=fixedModule ? [fixedModule] : [];
  const [searchParams,setSearchParams] = useSearchParams();
  const linkedArtifact = searchParams.get("upstream_artifact") || "";
  const linkedConfig = linkedArtifact ? {
    upstream_artifact_id: linkedArtifact,
    ...(fixedModule === "ml-analysis" ? {mode: "vj"} : {}),
    ...(fixedModule === "mait-nkt" ? {tra_source: "pep_analysis"} : {}),
  } : {};
  const initialConfigs=fixedModule ? {[fixedModule]: {...linkedConfig, ...tool?.preset}} : {};
  const initialProjectId = searchParams.get("project") || searchParams.get("project_id") || sharedData?.projectId || "";
  const requestedAssetSet = searchParams.get("asset_set") || "";
  const sharedContextMatches = sharedData?.projectId === initialProjectId && (!requestedAssetSet || sharedData.assetSetName === requestedAssetSet);
  const [wizard, setWizard] = useState<WizardState>({ ...INITIAL_STATE, ...(sharedContextMatches ? sharedData : {}), projectId: initialProjectId, assetSetName:requestedAssetSet || (sharedContextMatches ? sharedData.assetSetName : ""), selectedModules:initialModules, moduleConfigs:initialConfigs });
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [batchStatuses, setBatchStatuses] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [showHistory, setShowHistory] = useState(Boolean(searchParams.get("job")));
  const inspectionVersion = useRef(0);
  useEffect(() => () => { inspectionVersion.current += 1; }, []);

  // Load legacy Script Hub modules from the Flask single-machine module catalog.
  const modulesState = useApi(() => listScriptHubModules(), []);
  const availableModules = modulesState.status === "ready" ? modulesState.data.modules.filter(module=>!fixedModule || module.key===fixedModule) : [];

  const completedSteps: number[] = [];
  if (wizard.pepPaths.length > 0 || wizard.profilePath || wizard.transcriptomePath || wizard.deconvolutionPath)
    completedSteps.push(0);
  if (wizard.inspection) completedSteps.push(1);
  if (wizard.selectedModules.length) completedSteps.push(2);
  if (wizard.jobIds.length) completedSteps.push(3);
  if (Object.keys(wizard.resultsByJobId).length) completedSteps.push(4);

  /* ── Navigation ── */
  const goToStage = useCallback((stage: number) => {
    setWizard((prev) => ({ ...prev, stage: Math.max(1, Math.min(5, stage)) }));
  }, []);

  const handleNext = useCallback(() => {
    setWizard((prev) => ({ ...prev, stage: Math.min(5, prev.stage + 1) }));
  }, []);

  const handleBack = useCallback(() => {
    setWizard((prev) => ({ ...prev, stage: Math.max(1, prev.stage - 1) }));
  }, []);

  /* ── Stage callbacks ── */
  const handleDataUpdate = useCallback(
    (data: { projectId: string; assetSetName: string; pepPaths: string[]; profilePath: string; transcriptomePath: string; deconvolutionPath?: string }) => {
      setBatchStatuses([]);
      inspectionVersion.current += 1;
      const sameLinkedDataset = data.projectId === initialProjectId && data.assetSetName === searchParams.get("asset_set");
      shareData(data);
      setSearchParams(previous=>{const next=new URLSearchParams(previous);next.set("project",data.projectId);if(data.assetSetName) next.set("asset_set",data.assetSetName); else next.delete("asset_set");next.delete("job");next.delete("batch");if (!sameLinkedDataset) next.delete("upstream_artifact");return next;},{replace:true});
      setWizard((prev) => ({
        ...prev,
        projectId: data.projectId,
        assetSetName: data.assetSetName,
        pepPaths: data.pepPaths,
        profilePath: data.profilePath,
        transcriptomePath: data.transcriptomePath,
        deconvolutionPath: data.deconvolutionPath || "",
        inspection: null,
        selectedModules: initialModules,
        moduleConfigs: sameLinkedDataset ? initialConfigs : (fixedModule ? {[fixedModule]: {...tool?.preset}} : {}),
        jobIds: [],
        resultsByJobId: {},
      }));
      setInspectionError(null);
    },
    [fixedModule,tool,shareData,setSearchParams,linkedArtifact,initialProjectId,searchParams],
  );

  const handleInspect = useCallback(async (mappingChanged = false) => {
    if (mappingChanged) {
      setWizard(previous => ({...previous, inspection: null,
        moduleConfigs: fixedModule ? {[fixedModule]: {...tool?.preset}} : {},
        jobIds: [], resultsByJobId: {},
      }));
      setBatchStatuses([]);
      setSearchParams(previous => {
        const next = new URLSearchParams(previous);
        next.delete("upstream_artifact"); next.delete("job"); next.delete("batch");
        return next;
      }, {replace: true});
    }
    const version = ++inspectionVersion.current;
    setInspectionError(null);
    try {
      const data = await inspectScriptHubDataSelection({
        project_id: wizard.projectId || undefined,
        asset_set: wizard.assetSetName || undefined,
        pep_paths: wizard.pepPaths,
        profile_path: wizard.profilePath || undefined,
        transcriptome_path: wizard.transcriptomePath || undefined,
        deconvolution_path: wizard.deconvolutionPath || undefined,
      });

      if (version !== inspectionVersion.current) return;
      const chains = Array.isArray(data.chains) ? data.chains : [];
      const sampleNames = Array.isArray(data.samples) ? data.samples.map(String).filter(Boolean) : [];
      const profileColumns = Array.isArray(data.profile_columns) ? data.profile_columns : [];
      const groupFields = Array.isArray(data.group_fields) ? data.group_fields : [];
      const pepColumns = Array.isArray(data.pep_columns) ? data.pep_columns : [];
      const resolvedProfilePath = data.profile_path || wizard.profilePath;
      const resolvedPepPreviewPath = chooseRandomPepPreviewPath(
        data.random_pep_preview_file,
        data.pep_files_preview,
        wizard.pepPaths,
      );
      const previewWarnings: string[] = [];
      const [profilePreviewResult, pepPreviewResult] = await Promise.allSettled([
        resolvedProfilePath ? readScriptHubTablePreview(resolvedProfilePath) : Promise.resolve(null),
        resolvedPepPreviewPath ? readScriptHubTablePreview(resolvedPepPreviewPath) : Promise.resolve(null),
      ]);
      if (version !== inspectionVersion.current) return;
      const profilePreview = profilePreviewResult.status === "fulfilled"
        ? tablePreviewFromResponse(profilePreviewResult.value)
        : undefined;
      const pepPreview = pepPreviewResult.status === "fulfilled"
        ? tablePreviewFromResponse(pepPreviewResult.value)
        : undefined;

      if (profilePreviewResult.status === "rejected") {
        previewWarnings.push(`Profile 预览失败： ${profilePreviewResult.reason instanceof Error ? profilePreviewResult.reason.message : "无法读取数据表"}`);
      }
      if (pepPreviewResult.status === "rejected") {
        previewWarnings.push(`PEP 预览失败： ${pepPreviewResult.reason instanceof Error ? pepPreviewResult.reason.message : "无法读取数据表"}`);
      }

      const inspection: InspectionResult = {
        inputQuality: data.input_quality,
        samples: Number(data.sample_count || 0),
        sampleNames,
        chains: Number(data.chain_count ?? chains.length),
        chainLabels: chains,
        pepFiles: Number(data.pep_file_count || 0),
        profileLoaded: Boolean(data.profile_path || profileColumns.length > 0),
        transcriptomeLoaded: Boolean(data.transcriptome_path || wizard.transcriptomePath),
        deconvolutionLoaded: Boolean(data.deconvolution_path),
        warnings: Array.isArray(data.warnings) ? data.warnings : [],
        profileFields: profileColumns,
        groupFields,
        pepColumns,
        profilePreview,
        pepPreview,
      };

      inspection.warnings = [...inspection.warnings, ...previewWarnings];

      setWizard((prev) => ({
        ...prev,
        pepPaths: data.pep_paths?.length ? data.pep_paths : prev.pepPaths,
        profilePath: resolvedProfilePath || prev.profilePath,
        transcriptomePath: data.transcriptome_path || prev.transcriptomePath,
        deconvolutionPath: data.deconvolution_path || prev.deconvolutionPath,
        inspection,
      }));
    } catch (err) {
      if (version !== inspectionVersion.current) return;
      const message = err instanceof Error ? err.message : "数据检查失败";
      setInspectionError(message);
      if (mappingChanged) throw err;
    }
  }, [wizard.projectId, wizard.assetSetName, wizard.pepPaths, wizard.profilePath, wizard.transcriptomePath, wizard.deconvolutionPath, fixedModule, tool, setSearchParams]);

  const handleModuleUpdate = useCallback(
    (selectedModules: string[], moduleConfigs: Record<string, Record<string, unknown>>) => {
      setWizard((prev) => ({
        ...prev,
        selectedModules: fixedModule ? [fixedModule] : selectedModules,
        moduleConfigs: fixedModule ? {[fixedModule]: {...moduleConfigs[fixedModule],...tool?.preset}} : moduleConfigs,
        jobIds: [],
        resultsByJobId: {},
      }));
    },
    [fixedModule,tool,shareData,setSearchParams,linkedArtifact,initialProjectId,searchParams],
  );

  const handleJobsCreated = useCallback((jobIds: string[]) => {
    setWizard((prev) => ({ ...prev, jobIds }));
    setSearchParams(previous=>{const next=new URLSearchParams(previous);if(jobIds[0] && !next.has("batch")) next.set("job",jobIds[0]);next.set("project",wizard.projectId);return next;},{replace:true});
  }, [setSearchParams,wizard.projectId]);

  const handleComplete = useCallback((resultsByJobId: Record<string, JobResultsResponse>) => {
    setWizard((prev) => ({ ...prev, resultsByJobId }));
  }, []);

  const handleReset = useCallback(() => {
    setBatchStatuses([]);
    inspectionVersion.current += 1;
    setInspectionError(null);
    setSearchParams(previous=>{const next=new URLSearchParams(previous);next.delete("job");next.delete("batch");next.delete("upstream_artifact");return next;},{replace:true});
    setWizard((prev) => ({
        ...prev,
        stage: 1,

        inspection: null,
      selectedModules: initialModules,
      moduleConfigs: fixedModule ? {[fixedModule]: {...tool?.preset}} : {},
      jobIds: [],
      resultsByJobId: {},
    }));
  }, [fixedModule,tool,setSearchParams]);

  const sourceContext = wizard.inspection
    ? {
        projectId: wizard.projectId,
        assetSetId: wizard.assetSetName,
        profilePath: wizard.profilePath,
        pepPaths: wizard.pepPaths,
        transcriptomePath: wizard.transcriptomePath,
        deconvolutionPath: wizard.deconvolutionPath,
        chains: wizard.inspection.chainLabels,
        sampleNames: wizard.inspection.sampleNames,
        profileFields: wizard.inspection.profileFields,
        groupFields: wizard.inspection.groupFields,
        pepColumns: wizard.inspection.pepColumns,
        profilePreview: wizard.inspection.profilePreview,
        pepPreview: wizard.inspection.pepPreview,
      }
    : undefined;

  const presetInputReady = !tool?.preset?.input_mode || (tool.preset.input_mode === "expression" ? !!wizard.transcriptomePath : wizard.pepPaths.length > 0);

  /* ── Validation ── */
  const canProceed = () => {
    const s = wizard.stage;
    if (s === 1)
      return (
        wizard.projectId &&
        (wizard.pepPaths.length > 0 || !!wizard.profilePath || !!wizard.transcriptomePath || !!wizard.deconvolutionPath)
      );
    if (s === 2) return !!wizard.inspection && !wizard.inspection.inputQuality?.errors.length && presetInputReady && hasAnySelectableModule(availableModules, sourceContext);
    if (s === 3) {
      return presetInputReady && wizard.selectedModules.length > 0 && wizard.selectedModules.every((key) => {
        const selected = availableModules.find((module) => module.key === key);
        return isModuleSelectable(selected, sourceContext);
      });
    }
    if (s === 4) return !running && wizard.jobIds.length > 0 && wizard.jobIds.every((id) => Boolean(wizard.resultsByJobId[id]));
    if (s === 5) return Object.keys(wizard.resultsByJobId).length > 0;
    return true; // stage 6 always can proceed (it's the end)
  };

  const stageGateMessage = (() => {
    if (wizard.stage !== 2 || !wizard.inspection) return "";
    if (wizard.inspection.inputQuality?.errors.length) return "请先修正上方输入问题，再重新检查数据。";
    if (presetInputReady && hasAnySelectableModule(availableModules, sourceContext)) return "";
    return tool ? `当前数据尚不满足「${tool.title}」的输入要求，或运行环境未启用。所需输入：${tool.input}。` : "当前数据集尚不满足任何分析模块的输入要求，请返回补充 PEP、Profile 或转录组数据。";
  })();

  /* ── Build stepper steps ── */
  const stepperSteps: StepDef[] = WIZARD_STEPS.map((label,index) => ({ label:tool && index===2 ? "配置参数与分组" : label }));

  const isFirstStage = wizard.stage === 1;
  const isLastStage = wizard.stage === 5;

  return (
    <div
      style={{
        width: "100%",
        maxWidth: "100%",
        margin: "0 auto",
        padding: "clamp(var(--spacing-md), 1.5vw, var(--spacing-2xl))",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-2xl)",
      }}
    >
      <PageHeader
        title={tool?.title || "组合分析"}
        subtitle={tool ? `${tool.description} 所需输入：${tool.input}` : `第 ${wizard.stage} / ${WIZARD_STEPS.length} 步 · ${WIZARD_STEPS[wizard.stage - 1]}`}
      >
        <span
          style={{
            fontSize: "0.78rem",
            color: "var(--text-tertiary)",
            background: "var(--bg-inset)",
            padding: "4px 12px",
            borderRadius: "var(--radius-pill)",
          }}
        >
          当前数据集：{wizard.assetSetName || "尚未选择"}
        </span>
        <button className="btn btn-secondary" onClick={() => setShowHistory(value => !value)}>
          {showHistory ? "返回当前分析" : "查看分析历史"}
        </button>
        <a className="btn btn-secondary" href="/guide" target="_blank" rel="noreferrer">使用指南与示例数据</a>
      </PageHeader>

      {showHistory && <Stage6History moduleFilter={fixedModule === "charts" ? "charts.combined" : fixedModule} initialJobId={searchParams.get("job") || undefined} projectId={wizard.projectId} onSelectResult={() => { handleReset(); setShowHistory(false); }} />}
      <div hidden={showHistory} style={{ display: showHistory ? "none" : "grid", gridTemplateColumns: "minmax(0, 1fr)", minWidth: 0, gap: "var(--spacing-2xl)" }}>
      {modulesState.status === "error" && <p role="alert">分析目录读取失败：{modulesState.error}<button className="btn btn-secondary" onClick={modulesState.refetch}>重新读取</button></p>}
      {/* Stepper */}
      <Stepper steps={stepperSteps} currentStep={wizard.stage - 1} />

      {/* Stage Content */}
      <div style={{ minHeight: "400px", minWidth: 0 }}>
        {wizard.stage === 1 && !showHistory && (
          <Stage1DataIntake
            assetSetName={wizard.assetSetName}
            projectId={wizard.projectId}
            pepPaths={wizard.pepPaths}
            profilePath={wizard.profilePath}
            transcriptomePath={wizard.transcriptomePath}
            deconvolutionPath={wizard.deconvolutionPath}
            onUpdate={handleDataUpdate}
          />
        )}

        {wizard.stage === 2 && (
          <Stage2SourceInspection
            projectId={wizard.projectId}
            assetSet={wizard.assetSetName}
            pepPaths={wizard.pepPaths}
            profilePath={wizard.profilePath}
            transcriptomePath={wizard.transcriptomePath}
            deconvolutionPath={wizard.deconvolutionPath}
            inspection={wizard.inspection}
            inspectionError={inspectionError}
            onInspect={handleInspect}
          />
        )}

        {wizard.stage === 3 && (
          <Stage3ModuleConfig
            fixedModule={fixedModule}
            fixedParameters={tool?.preset}
            modules={availableModules}
            projectId={wizard.projectId}
            selectedModules={wizard.selectedModules}
            moduleConfigs={wizard.moduleConfigs}
            sourceContext={sourceContext}
            onUpdate={handleModuleUpdate}
          />
        )}

        {wizard.stage === 4 && (
          <Stage4Execution
            onBatchStatuses={setBatchStatuses}
            onBatchCreated={jobId => setSearchParams(previous => { const next = new URLSearchParams(previous); next.set("batch", jobId); next.set("job", jobId); return next; }, {replace: true})}
            projectId={wizard.projectId}
            modules={wizard.selectedModules}
            baseConfig={{
              selected_chains: wizard.inspection?.chainLabels || [],
              group_fields: wizard.inspection?.groupFields || [],
              project_id: wizard.projectId,
              asset_set: wizard.assetSetName,
              pep_paths: wizard.pepPaths,
              profile_path: wizard.profilePath,
              transcriptome_path: wizard.transcriptomePath,
              deconvolution_path: wizard.deconvolutionPath,
            }}
            moduleConfigs={wizard.moduleConfigs}
            jobIds={wizard.jobIds}
            onJobsCreated={handleJobsCreated}
            onComplete={handleComplete}
            onRunningChange={setRunning}
          />
        )}

        {wizard.stage === 5 && (
          <Stage5Results
            batchStatuses={batchStatuses}
            expectedCount={wizard.selectedModules.length}
            jobIds={wizard.jobIds}
            resultsByJobId={wizard.resultsByJobId}
            onReset={handleReset}
          />
        )}
      </div>

      {stageGateMessage && (
        <div
          style={{
            padding: "10px 14px",
            borderRadius: "var(--radius-control)",
            border: "1px solid rgba(255,149,0,0.28)",
            background: "rgba(255,149,0,0.08)",
            color: "var(--warning)",
            fontSize: "0.84rem",
          }}
        >
          {stageGateMessage}
        </div>
      )}

      {/* Navigation Buttons */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          paddingTop: "var(--spacing-lg)",
          borderTop: "1px solid var(--separator)",
        }}
      >
        <button
          onClick={handleBack}
          disabled={isFirstStage || running}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 24px",
            borderRadius: "var(--radius-control)",
            border: isFirstStage ? "1px solid transparent" : "1px solid var(--separator)",
            background: isFirstStage ? "transparent" : "var(--bg-elevated)",
            color: isFirstStage ? "var(--text-tertiary)" : "var(--text-primary)",
            fontWeight: 500,
            fontSize: "0.9rem",
            cursor: isFirstStage ? "default" : "pointer",
            visibility: isFirstStage ? "hidden" : "visible",
          }}
        >
          <ArrowLeft size={16} />
          上一步
        </button>

        {!isLastStage && (
          <button
            onClick={handleNext}
            disabled={!canProceed()}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--spacing-sm)",
              padding: "10px 24px",
              borderRadius: "var(--radius-control)",
              background: canProceed() ? "var(--accent)" : "var(--bg-inset)",
              color: canProceed() ? "#fff" : "var(--text-tertiary)",
              fontWeight: 500,
              fontSize: "0.9rem",
              border: "none",
              cursor: canProceed() ? "pointer" : "not-allowed",
            }}
          >
            {wizard.stage === 4 ? "查看结果" : "下一步"}
            <ArrowRight size={16} />
          </button>
        )}

        {isLastStage && (
          <button
            onClick={handleReset}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--spacing-sm)",
              padding: "10px 24px",
              borderRadius: "var(--radius-control)",
              background: "var(--accent)",
              color: "#fff",
              fontWeight: 500,
              fontSize: "0.9rem",
              border: "none",
              cursor: "pointer",
            }}
          >
            <FlaskConical size={16} />
            开始新的分析
          </button>
        )}
      </div>
      </div>
    </div>
  );
}

function tablePreviewFromResponse(
  response: Awaited<ReturnType<typeof readScriptHubTablePreview>> | null,
): TablePreview | undefined {
  if (!response || !Array.isArray(response.columns) || !Array.isArray(response.rows)) return undefined;
  return {
    path: response.file_path,
    columns: response.columns,
    rows: response.rows,
    totalRows: Number(response.row_count || response.rows.length),
  };
}

export function chooseRandomPepPreviewPath(
  backendRandomFile?: ScriptHubPepPreview | null,
  previewFiles?: ScriptHubPepPreview[],
  fallbackPepPaths?: string[],
): string {
  if (backendRandomFile?.path) return backendRandomFile.path;

  const candidatePaths = [
    ...(previewFiles || []).map((item) => item.path),
    ...(fallbackPepPaths || []),
  ].filter((path): path is string => Boolean(path));

  if (!candidatePaths.length) return "";
  const randomIndex = Math.floor(Math.random() * candidatePaths.length);
  return candidatePaths[randomIndex] || candidatePaths[0];
}
