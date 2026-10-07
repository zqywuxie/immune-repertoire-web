import { getPreparationConfig } from "../../features/analysis/analysisPreparation";
import { AnalysisSelectionNotice } from "../../features/analysis/AnalysisSelectionNotice";
import { batchResultSource } from "../../features/scripthub/batchDependencies";
import { configurationIssue } from "../../features/scripthub/configurationValidation";
import { analysisLabel } from "../../shared/utils/analysisLabels";
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
import { getProject } from "../../shared/api/projects";
import { InputAssetNotice, inputAssetReturnPath, useInputAssetIntent } from "../../features/analysis/InputAssetIntent";
import { assetPath, getAssetSetName } from "../../features/assets/assetSets";
import { inspectScriptHubDataSelection, listScriptHubModules, readScriptHubTablePreview } from "../../shared/api/scriptHub";
import type { ScriptHubPepPreview } from "../../shared/api/scriptHub";
import { AnalysisInputReview } from "../../features/scripthub/AnalysisInputReview";
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
import { getCombinedInspectionScope, getModuleAvailability, hasAnySelectableModule, isModuleSelectable } from "../../features/scripthub/moduleRequirements";

import type { AnalysisTool } from "../../features/analysis/tools";
import { useAnalysisData, type AnalysisData } from "../../features/analysis/AnalysisDataContext";

/* ── Wizard State ── */
interface WizardState {
  stage: number; // 1-5
  projectId: string;
  assetSetName: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  deconvolutionPath?: string;
  inputAssets?: import("../../shared/types/domain").ProjectAsset[];
  selectionExplicit?: boolean;
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

const WIZARD_STEPS = ["选择数据", "选择与配置分析", "运行分析", "查看结果"];

export function ScriptHubWizard({tool}:{tool?:AnalysisTool} = {}) {
  const {data:sharedData,setData:shareData,selectionState="ready"}=useAnalysisData();
  const fixedModule=tool?.module;
  const initialModules=fixedModule ? [fixedModule] : [];
  const [searchParams,setSearchParams] = useSearchParams();
  const activeBatchId = useRef(searchParams.get("batch") || "");
  const [alignmentReviewed, setAlignmentReviewed] = useState(false);
  const [groupSpecIssue, setGroupSpecIssue] = useState("");
  const linkedArtifact = searchParams.get("upstream_artifact") || "";
  const linkedConfig = linkedArtifact ? {
    upstream_artifact_id: linkedArtifact,
    ...(fixedModule === "go-kegg-enrichment" ? {input_mode: "deg"} : {}),
    ...(fixedModule === "ml-analysis" ? {mode: "vj"} : {}),
    ...(fixedModule === "mait-nkt" ? {tra_source: "pep_analysis"} : {}),
  } : {};
  const initialConfigs=fixedModule ? {[fixedModule]: {...getPreparationConfig(tool?.id || "", searchParams.get("prepare_mode") || ""), ...linkedConfig, ...tool?.preset}} : {};
  const initialProjectId = searchParams.get("project") || searchParams.get("project_id") || sharedData?.projectId || "";
  const requestedAssetSet = searchParams.get("asset_set") || "";
  const requestedInputId = searchParams.get("input_asset") || "";
  const sharedContextMatches = (!requestedInputId || searchParams.get("reuse_inputs")==="1") && sharedData?.projectId === initialProjectId && (!searchParams.has("asset_set") || sharedData.assetSetName === requestedAssetSet);
  const [wizard, setWizard] = useState<WizardState>({ ...INITIAL_STATE, ...(sharedContextMatches ? sharedData : {}), projectId: initialProjectId, assetSetName:searchParams.has("asset_set") ? requestedAssetSet : (sharedContextMatches ? sharedData.assetSetName : ""), selectedModules:initialModules, moduleConfigs:initialConfigs });
  const restoreWaiting=useRef(Boolean(sharedContextMatches && selectionState!=="ready"));
  const restoringSelection=Boolean(sharedContextMatches && selectionState!=="ready");
  const inputIntent=useInputAssetIntent(wizard.projectId,wizard.assetSetName,requestedInputId);
  const requestedInputAsset=inputIntent.status==="ready"?inputIntent.data:null;
  const inputIntentPending=restoringSelection || Boolean(requestedInputId && (inputIntent.status!=="ready" || !requestedInputAsset));
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [batchStatuses, setBatchStatuses] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [showHistory, setShowHistory] = useState(Boolean(searchParams.get("job")));
  const inspectionVersion = useRef(0);
  const autoEnterConfiguration = useRef(Boolean(fixedModule));
  const [inspectionBusy, setInspectionBusy] = useState(false);
  useEffect(() => () => { inspectionVersion.current += 1; }, []);

  // Load legacy Script Hub modules from the Flask single-machine module catalog.
  const projectState = useApi(() => wizard.projectId ? getProject(wizard.projectId, {summaryOnly:true}) : Promise.resolve(null), [wizard.projectId]);
  const projectName = projectState.status === "ready" ? projectState.data?.name || "尚未选择" : projectState.status === "error" ? "读取失败" : "读取中…";
  const modulesState = useApi(() => listScriptHubModules(), []);
  const availableModules = modulesState.status === "ready" ? modulesState.data.modules.filter(module=>!fixedModule || module.key===fixedModule) : [];

  const completedSteps: number[] = [];
  if (wizard.stage >= 3 || wizard.inspection) completedSteps.push(0);
  if (wizard.stage >= 4 && wizard.selectedModules.length) completedSteps.push(1);
  if (Object.keys(wizard.resultsByJobId).length) completedSteps.push(2);

  /* ── Navigation ── */
  const goToStage = useCallback((stage: number) => {
    setWizard((prev) => ({ ...prev, stage: Math.max(1, Math.min(5, stage)) }));
  }, []);

  const handleNext = useCallback(() => {
    setWizard((prev) => ({ ...prev, stage: prev.stage === 1 ? 3 : Math.min(5, prev.stage + 1) }));
  }, [fixedModule]);

  const handleBack = useCallback(() => {
    autoEnterConfiguration.current = false;
    setWizard((prev) => ({ ...prev, stage: prev.stage === 3 ? 1 : Math.max(1, prev.stage - 1) }));
  }, [fixedModule]);

  /* ── Stage callbacks ── */
  const handleDataUpdate = useCallback(
    (data: AnalysisData, selectedAsset?: import("../../shared/types/domain").ProjectAsset) => {
      activeBatchId.current = "";
      setBatchStatuses([]);
      inspectionVersion.current += 1;
      setInspectionBusy(false);
      const sameLinkedDataset = data.projectId === initialProjectId && data.assetSetName === searchParams.get("asset_set");
      shareData(data);
      setSearchParams(previous=>{const next=new URLSearchParams(previous);next.set("project",data.projectId);next.set("reuse_inputs","1");if(data.assetSetName) next.set("asset_set",data.assetSetName); else next.delete("asset_set");next.delete("job");next.delete("batch");if(requestedInputAsset && ![...data.pepPaths,data.profilePath,data.transcriptomePath,data.deconvolutionPath].includes(assetPath(requestedInputAsset)))next.delete("input_asset");if((data.projectId!==wizard.projectId || data.assetSetName!==wizard.assetSetName) && (!requestedInputAsset || data.projectId!==requestedInputAsset.project_id || data.assetSetName!==getAssetSetName(requestedInputAsset)))next.delete("input_asset");if (!sameLinkedDataset) next.delete("upstream_artifact");if(selectedAsset && selectedAsset.project_id===data.projectId && getAssetSetName(selectedAsset)===data.assetSetName)next.set("input_asset",selectedAsset.id);return next;},{replace:true});
      setWizard((prev) => ({
        ...prev,
        projectId: data.projectId,
        assetSetName: data.assetSetName,
        pepPaths: data.pepPaths,
        profilePath: data.profilePath,
        transcriptomePath: data.transcriptomePath,
        deconvolutionPath: data.deconvolutionPath || "",
        inputAssets:data.inputAssets,
        selectionExplicit:data.selectionExplicit,
        inspection: null,
        selectedModules: initialModules,
        moduleConfigs: sameLinkedDataset ? initialConfigs : (fixedModule ? {[fixedModule]: {...tool?.preset}} : {}),
        jobIds: [],
        resultsByJobId: {},
      }));
      setInspectionError(null);
    },
    [fixedModule,tool,shareData,setSearchParams,linkedArtifact,initialProjectId,searchParams,requestedInputAsset,wizard.projectId,wizard.assetSetName],
  );

  useEffect(()=>{
    if(restoreWaiting.current && sharedContextMatches && selectionState==="ready" && sharedData){
      restoreWaiting.current=false;handleDataUpdate(sharedData);
    }
  },[sharedContextMatches,selectionState,sharedData,handleDataUpdate]);
  const inspectionScopeKey = JSON.stringify(getCombinedInspectionScope(
    fixedModule ? [fixedModule] : wizard.selectedModules, wizard.moduleConfigs, {transcriptomePath:wizard.transcriptomePath}));
  const inspectionMatchesMode = JSON.stringify({inputTypes:wizard.inspection?.inspectedInputTypes,alignmentGroups:wizard.inspection?.alignmentGroups}) === inspectionScopeKey;

  const handleInspect = useCallback(async (mappingChanged = false) => {
    if (inputIntentPending) return;
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
    setInspectionBusy(true);
    setInspectionError(null);
    try {
      const {inputTypes, alignmentGroups}: ReturnType<typeof getCombinedInspectionScope> = JSON.parse(inspectionScopeKey);
      const includes = (kind: string) => !inputTypes || inputTypes.some(input => input === kind);
      const data = await inspectScriptHubDataSelection({
        input_types: inputTypes,
        alignment_groups: alignmentGroups,
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
      const resolvedProfilePath = includes("profile") ? data.profile_path || wizard.profilePath : "";
      const resolvedPepPreviewPath = includes("pep") ? chooseRandomPepPreviewPath(
        data.random_pep_preview_file,
        data.pep_files_preview,
        wizard.pepPaths,
      ) : "";
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
        previewWarnings.push(`样本指标表预览失败： ${profilePreviewResult.reason instanceof Error ? profilePreviewResult.reason.message : "无法读取数据表"}`);
      }
      if (pepPreviewResult.status === "rejected") {
        previewWarnings.push(`克隆序列表预览失败： ${pepPreviewResult.reason instanceof Error ? pepPreviewResult.reason.message : "无法读取数据表"}`);
      }

      const inspection: InspectionResult = {
        inputQuality: data.input_quality,
        inspectedInputTypes: inputTypes,
        alignmentGroups,
        samples: Number(data.sample_count || 0),
        sampleNames,
        chains: Number(data.chain_count ?? chains.length),
        chainLabels: chains,
        pepFiles: Number(data.pep_file_count || 0),
        profileLoaded: Boolean(data.profile_path || profileColumns.length > 0),
        transcriptomeLoaded: includes("transcriptome") && Boolean(data.transcriptome_path || wizard.transcriptomePath),
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
        pepPaths: prev.pepPaths.length ? prev.pepPaths : data.pep_paths || [],
        profilePath: prev.profilePath || resolvedProfilePath,
        transcriptomePath: prev.transcriptomePath || data.transcriptome_path || "",
        deconvolutionPath: prev.deconvolutionPath || data.deconvolution_path || "",
        inspection,
      }));
    } catch (err) {
      if (version !== inspectionVersion.current) return;
      const message = err instanceof Error ? err.message : "数据检查失败";
      setInspectionError(message);
      if (mappingChanged) throw err;
    } finally {
      if (version === inspectionVersion.current) setInspectionBusy(false);
    }
  }, [wizard.projectId, wizard.assetSetName, wizard.pepPaths, wizard.profilePath, wizard.transcriptomePath, wizard.deconvolutionPath, inspectionScopeKey, fixedModule, tool, setSearchParams, inputIntentPending]);

  const handleModuleUpdate = useCallback(
    (selectedModules: string[], moduleConfigs: Record<string, Record<string, unknown>>) => {
      const nextModules = fixedModule ? [fixedModule] : selectedModules;
      const nextConfigs = fixedModule ? {[fixedModule]: {...moduleConfigs[fixedModule],...tool?.preset}} : moduleConfigs;
      const nextScope = JSON.stringify(getCombinedInspectionScope(nextModules, nextConfigs, {transcriptomePath:wizard.transcriptomePath}));
      if (nextScope !== inspectionScopeKey || !nextModules.length) {
        inspectionVersion.current += 1;
        setInspectionBusy(false);
        setInspectionError(null);
      }
      setWizard((prev) => ({
        ...prev, selectedModules: nextModules, moduleConfigs: nextConfigs,
        ...(nextScope !== inspectionScopeKey || !nextModules.length ? {inspection:null} : {}),
        jobIds: [], resultsByJobId: {},
      }));
    },
    [fixedModule,tool,inspectionScopeKey,wizard.transcriptomePath],
  );

  const handleJobsCreated = useCallback((jobIds: string[]) => {
    setWizard((prev) => ({ ...prev, jobIds }));
    setSearchParams(previous=>{const next=new URLSearchParams(previous);
      if (activeBatchId.current) {next.set("batch",activeBatchId.current);next.set("job",activeBatchId.current);}
      else if (jobIds[0]) next.set("job",jobIds[0]);
      next.set("project",wizard.projectId);return next;
    },{replace:true});
  }, [setSearchParams,wizard.projectId]);

  const handleComplete = useCallback((resultsByJobId: Record<string, JobResultsResponse>) => {
    setWizard((prev) => ({ ...prev, resultsByJobId }));
  }, []);

  const handleReset = useCallback(() => {
    activeBatchId.current = "";
    setBatchStatuses([]);
    inspectionVersion.current += 1;
    autoEnterConfiguration.current = Boolean(fixedModule);
    setInspectionBusy(false);
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

  const sourceContext = wizard.projectId ? {
    projectId: wizard.projectId, assetSetId: wizard.assetSetName,
    profilePath: wizard.profilePath, pepPaths: wizard.pepPaths,
    transcriptomePath: wizard.transcriptomePath, deconvolutionPath: wizard.deconvolutionPath,
    artifactModules: Object.entries(wizard.moduleConfigs).filter(([,config]) => Boolean(config.upstream_artifact_id)).map(([key]) => key),
    inspectedInputTypes: wizard.inspection?.inspectedInputTypes,
    chains: wizard.inspection?.chainLabels || [], sampleNames: wizard.inspection?.sampleNames || [],
    profileFields: wizard.inspection?.profileFields || [], groupFields: wizard.inspection?.groupFields || [],
    pepColumns: wizard.inspection?.pepColumns || [],
    profilePreview: wizard.inspection?.profilePreview, pepPreview: wizard.inspection?.pepPreview,
  } : undefined;

  const fixedAvailability = fixedModule
    ? getModuleAvailability(availableModules.find(module=>module.key===fixedModule), sourceContext, wizard.moduleConfigs[fixedModule] || {}) : null;
  const configuredInputsReady = fixedAvailability ? fixedAvailability.selectable : hasAnySelectableModule(availableModules, sourceContext);

  const inspectedQuality = inspectionMatchesMode ? wizard.inspection?.inputQuality : undefined;
  const inputMappingRequired = Boolean(inspectedQuality?.inputs?.some(input => ["profile", "transcriptome", "deconvolution"].includes(input.kind) && input.status === "needs_mapping" && !input.sample_column));
  const alignmentMismatch = Boolean(inspectedQuality?.alignments?.some(item => item.missing_count || item.extra_count));
  useEffect(() => { setAlignmentReviewed(false); }, [wizard.inspection]);
  const validationPending = Boolean(inspectedQuality?.inputs.some(input => input.status === "pending"));
  const selectedDataReady = Boolean(!inputIntentPending && wizard.projectId && wizard.assetSetName &&
    (wizard.pepPaths.length || wizard.profilePath || wizard.transcriptomePath || wizard.deconvolutionPath || linkedArtifact || (fixedModule && JSON.parse(inspectionScopeKey).inputTypes.length===0)));

  // Inspect only selected modules; a new scope supersedes an in-flight check.
  useEffect(() => {
    if (showHistory || wizard.stage > 3 || inspectionBusy || inspectionError || !selectedDataReady ||
        (!fixedModule && (wizard.stage !== 3 || !wizard.selectedModules.length))) return;
    if (!inspectionMatchesMode) {
      void handleInspect();
      return;
    }
    if (!validationPending) return;
    const timer = setTimeout(() => { void handleInspect(); }, 3000);
    return () => clearTimeout(timer);
  }, [showHistory, wizard.stage, fixedModule, wizard.selectedModules.length, inspectionBusy, inspectionError,
      selectedDataReady, inspectionMatchesMode, validationPending, handleInspect]);

  useEffect(() => {
    if (!autoEnterConfiguration.current || !fixedModule || wizard.stage !== 1 || showHistory || inspectionBusy || inspectionError ||
        !wizard.inspection || !inspectionMatchesMode || validationPending || inputMappingRequired || (alignmentMismatch && !alignmentReviewed) ||
        wizard.inspection.inputQuality?.errors.length || !configuredInputsReady) return;
    autoEnterConfiguration.current = false;
    setWizard(previous => ({...previous, stage: 3}));
  }, [fixedModule, wizard.stage, wizard.inspection, showHistory, inspectionBusy, inspectionError, validationPending,
      inputMappingRequired, alignmentMismatch, alignmentReviewed, inspectionMatchesMode, configuredInputsReady, availableModules, sourceContext]);

  const configurationPayload = (module:string):Record<string,unknown> => ({
    selected_chains: wizard.inspection?.chainLabels || [], group_fields: wizard.inspection?.groupFields || [],
    project_id: wizard.projectId, asset_set: wizard.assetSetName, pep_paths: wizard.pepPaths,
    profile_path: wizard.profilePath, transcriptome_path: wizard.transcriptomePath, deconvolution_path: wizard.deconvolutionPath,
    ...(wizard.moduleConfigs[module] || {}),
  });
  const configurationReview = wizard.selectedModules.map(module => {
    const source = batchResultSource(module, wizard.selectedModules, configurationPayload);
    return {module, label:analysisLabel(module), issue:configurationIssue(module, configurationPayload(module), Boolean(source)),
      possibleSource:source ? analysisLabel(source) : undefined};
  });
  const configurationReady = !groupSpecIssue && configurationReview.every(item=>!item.issue);

  /* ── Validation ── */
  const canProceed = () => {
    if(inputIntentPending)return false;
    const s = wizard.stage;
    if (s === 1 && !fixedModule)
      return (
        wizard.projectId &&
        (wizard.pepPaths.length > 0 || !!wizard.profilePath || !!wizard.transcriptomePath || !!wizard.deconvolutionPath || !!linkedArtifact)
      );
    if (s === 2 || (fixedModule && s === 1)) return inspectionMatchesMode && !inspectionError && !inspectionBusy && !validationPending && !inputMappingRequired && (!alignmentMismatch || alignmentReviewed) && !!wizard.inspection && !wizard.inspection.inputQuality?.errors.length && configuredInputsReady;
    if (s === 3) {
      return !inspectionBusy && !inspectionError && inspectionMatchesMode && !validationPending && !inputMappingRequired &&
        (!alignmentMismatch || alignmentReviewed) && !wizard.inspection?.inputQuality?.errors.length && configuredInputsReady && configurationReady && wizard.selectedModules.length > 0 && wizard.selectedModules.every((key) => {
        const selected = availableModules.find((module) => module.key === key);
        return isModuleSelectable(selected, sourceContext, fixedModule ? wizard.moduleConfigs[key] || {} : undefined) && (!["immune-infiltration","immune-infiltration-consistency","immune-infiltration-concordance","immune-infiltration-paired","immune-infiltration-pathway","immune-infiltration-sample-pathway"].includes(key) || wizard.moduleConfigs[key]?.infiltration_checked === true);
      });
    }
    if (s === 4) return !running && wizard.jobIds.length > 0 && wizard.jobIds.every((id) => Boolean(wizard.resultsByJobId[id]));
    if (s === 5) return Object.keys(wizard.resultsByJobId).length > 0;
    return true; // stage 6 always can proceed (it's the end)
  };

  const stageGateMessage = (() => {
    if ((wizard.stage !== 2 && !(fixedModule && wizard.stage === 1)) || !wizard.inspection) return "";
    if (validationPending) return "数据正在后台校验，完成后将自动更新。";
    if (wizard.inspection.inputQuality?.errors.length) return "请先修正上方输入问题，再重新检查数据。";
    if (inputMappingRequired) return "请先在上方“工作表、编号列与样本编号对应”中完成样本编号列或基因编号列映射，再重新检查数据。";
    if (alignmentMismatch && !alignmentReviewed) return "请核对上方样本匹配情况，并确认已了解各输入的样本范围。";
    if (configuredInputsReady) return "";
    return tool ? `当前数据尚不满足「${tool.title}」的输入要求，或运行环境未启用。${fixedAvailability?.reason || "请确认本次输入。"}` : "当前数据集尚不满足任何分析模块的输入要求，请返回补充克隆序列表、样本指标表或转录组数据。";
  })();

  /* ── Build stepper steps ── */
  const stepperSteps: StepDef[] = (fixedModule ? ["确认数据", "配置分析", "运行与结果"] : WIZARD_STEPS).map(label => ({label}));
  const displayedStep = wizard.stage <= 2 ? 0 : wizard.stage === 3 ? 1 : wizard.stage === 4 ? 2 : fixedModule ? 2 : 3;
  const resultsReady = !running && wizard.jobIds.length > 0 && wizard.jobIds.every(id => Boolean(wizard.resultsByJobId[id]));

  const isFirstStage = wizard.stage === 1;
  const isLastStage = wizard.stage === 5 || Boolean(fixedModule && wizard.stage === 4);

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
        subtitle={tool ? tool.description : `第 ${displayedStep + 1} / ${WIZARD_STEPS.length} 步 · ${WIZARD_STEPS[displayedStep]}`}
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
          当前项目：{projectName} · 数据集：{wizard.assetSetName || "尚未选择"}
        </span>
        <button className="btn btn-secondary" onClick={() => setShowHistory(value => !value)}>
          {showHistory ? "返回当前分析" : "查看分析历史"}
        </button>
        <a className="btn btn-secondary" href="/guide" target="_blank" rel="noreferrer">使用指南与示例数据</a>
      </PageHeader>

      {showHistory && <Stage6History moduleFilter={fixedModule === "charts" ? "charts.combined" : fixedModule} initialJobId={searchParams.get("job") || undefined} projectId={wizard.projectId} onSelectResult={() => { handleReset(); setShowHistory(false); }} />}
      <div hidden={showHistory} style={{ display: showHistory ? "none" : "grid", gridTemplateColumns: "minmax(0, 1fr)", minWidth: 0, gap: "var(--spacing-2xl)" }}>
      {projectState.status === "error" && <p role="alert">项目读取失败：{projectState.error}<button className="btn btn-secondary" onClick={projectState.refetch}>重新读取项目</button></p>}
      {modulesState.status === "error" && <p role="alert">分析目录读取失败：{modulesState.error}<button className="btn btn-secondary" onClick={modulesState.refetch}>重新读取</button></p>}
      {/* Stepper */}
      <Stepper steps={stepperSteps} currentStep={displayedStep} />

      {requestedInputId && !showHistory && <InputAssetNotice asset={requestedInputAsset} loading={inputIntent.status==="loading" || inputIntent.status==="idle"} error={inputIntent.status==="error"?inputIntent.error:null} returnPath={inputAssetReturnPath(wizard.projectId,requestedInputAsset,searchParams.get("return_to") || "")} onRetry={inputIntent.refetch} onClear={()=>{setSearchParams(previous=>{const next=new URLSearchParams(previous);next.delete("input_asset");return next;},{replace:true});setWizard(previous=>({...previous,...INITIAL_STATE,projectId:previous.projectId,assetSetName:previous.assetSetName,selectedModules:initialModules,moduleConfigs:initialConfigs}));autoEnterConfiguration.current=false;}}/>}
      {inspectionBusy && !showHistory && <p role="status" style={{margin:0,color:"var(--text-secondary)"}}>正在核对已登记数据…</p>}

      {(!requestedInputId || searchParams.get("reuse_inputs")==="1") && <AnalysisSelectionNotice projectId={wizard.projectId} dataset={wizard.assetSetName} onClear={()=>{
        restoreWaiting.current=false;
        const emptyData={projectId:wizard.projectId,assetSetName:wizard.assetSetName,pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:"",inputAssets:[],selectionExplicit:false};
        shareData(emptyData);setWizard(previous=>({...previous,...emptyData,inputAssets:[],selectionExplicit:false,inspection:null}));
        setSearchParams(previous=>{const next=new URLSearchParams(previous);next.delete("input_asset");return next;},{replace:true});
      }}/>}
      {/* Stage Content */}
      <div style={{ minHeight: "400px", minWidth: 0 }}>
        {wizard.stage === 1 && !showHistory && (
          <Stage1DataIntake
            requestedAsset={requestedInputAsset || undefined}
            allowDefaultDataset={!searchParams.has("asset_set")}
            inputAssets={wizard.inputAssets}
            selectionExplicit={wizard.selectionExplicit}
            inputIntentPending={inputIntentPending}
            assetSetName={wizard.assetSetName}
            projectId={wizard.projectId}
            pepPaths={wizard.pepPaths}
            profilePath={wizard.profilePath}
            transcriptomePath={wizard.transcriptomePath}
            deconvolutionPath={wizard.deconvolutionPath}
            onUpdate={handleDataUpdate}
          />
        )}

        {(wizard.stage === 2 || (fixedModule && wizard.stage === 1 && wizard.projectId && (wizard.pepPaths.length > 0 || wizard.profilePath || wizard.transcriptomePath || wizard.deconvolutionPath || linkedArtifact))) && (<>
          <Stage2SourceInspection
            inputAssets={wizard.inputAssets}
            projectId={wizard.projectId}
            assetSet={wizard.assetSetName}
            inputTypes={JSON.parse(inspectionScopeKey).inputTypes}
            pepPaths={inspectionScopeKey.includes('"pep"') ? wizard.pepPaths : []}
            profilePath={inspectionScopeKey.includes('"profile"') ? wizard.profilePath : ""}
            transcriptomePath={inspectionScopeKey.includes('"transcriptome"') ? wizard.transcriptomePath : ""}
            deconvolutionPath={inspectionScopeKey.includes('"deconvolution"') ? wizard.deconvolutionPath : ""}
            inspection={wizard.inspection}
            inspectionError={inspectionError}
            inspecting={inspectionBusy}
            onInspect={handleInspect}
          />
          {alignmentMismatch && <label style={{display:"flex",gap:10,padding:16,background:"var(--bg-inset)",borderRadius:10}}><input type="checkbox" checked={alignmentReviewed} onChange={event => setAlignmentReviewed(event.target.checked)} />我已核对样本匹配情况，了解各模块将按其要求使用对应样本；本操作不自动合并或删除样本。</label>}
          </>)}

        {wizard.stage === 3 && (<>
          {(fixedModule || wizard.selectedModules.length > 0) && <AnalysisInputReview
            assetSet={wizard.assetSetName} projectId={wizard.projectId}
            inputTypes={JSON.parse(inspectionScopeKey).inputTypes} inspection={inspectionMatchesMode ? wizard.inspection : null}
            inspecting={inspectionBusy || (!inspectionMatchesMode && !inspectionError)} inspectionError={inspectionError}
            validationPending={validationPending} needsMapping={inputMappingRequired}
            alignmentMismatch={alignmentMismatch} alignmentReviewed={alignmentReviewed}
            onAlignmentReviewed={setAlignmentReviewed} onInspect={handleInspect}
            pepPaths={wizard.pepPaths} profilePath={wizard.profilePath}
            transcriptomePath={wizard.transcriptomePath} deconvolutionPath={wizard.deconvolutionPath}
            onChangeData={() => {autoEnterConfiguration.current = false; goToStage(1);}}
          />}
          <Stage3ModuleConfig
            configurationReview={configurationReview}
            onGroupSpecIssue={setGroupSpecIssue}
            fixedModule={fixedModule}
            fixedParameters={tool?.preset}
            modules={availableModules}
            projectId={wizard.projectId}
            selectedModules={wizard.selectedModules}
            moduleConfigs={wizard.moduleConfigs}
            sourceContext={sourceContext}
            onUpdate={handleModuleUpdate}
          />
        </>)}

        {wizard.stage === 4 && (
          <Stage4Execution
            onBatchStatuses={setBatchStatuses}
            onBatchCreated={jobId => { activeBatchId.current = jobId; setSearchParams(previous => { const next = new URLSearchParams(previous); next.set("batch", jobId); next.set("job", jobId); return next; }, {replace: true}); }}
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
              sample_alignment_reviewed: alignmentReviewed,
            }}
            moduleConfigs={wizard.moduleConfigs}
            jobIds={wizard.jobIds}
            onJobsCreated={handleJobsCreated}
            onComplete={handleComplete}
            onRunningChange={setRunning}
          />
        )}

        {(wizard.stage === 5 || (fixedModule && wizard.stage === 4 && resultsReady)) && (
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
          disabled={isFirstStage || running || (wizard.stage === 4 && wizard.jobIds.length > 0)}
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

        {isLastStage && (!fixedModule || resultsReady) && (
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
