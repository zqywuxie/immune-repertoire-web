import { useState, useCallback } from "react";
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
import { Stage5Results } from "../../features/scripthub/stages/Stage5Results";
import type { InspectionResult } from "../../features/scripthub/stages/Stage2SourceInspection";
import type { TablePreview } from "../../features/scripthub/stages/Stage2SourceInspection";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { hasAnySelectableModule, isModuleSelectable } from "../../features/scripthub/moduleRequirements";

/* ── Wizard State ── */
interface WizardState {
  stage: number; // 1-5
  projectId: string;
  assetSetName: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
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
  inspection: null,
  selectedModules: [],
  moduleConfigs: {},
  jobIds: [],
  resultsByJobId: {},
};

const WIZARD_STEPS = [
  "Data Intake",
  "Source Inspection",
  "Module Config",
  "Execution",
  "Results",
];

export function ScriptHubWizard() {
  const [searchParams] = useSearchParams();
  const initialProjectId = searchParams.get("project") || searchParams.get("project_id") || "";
  const [wizard, setWizard] = useState<WizardState>({ ...INITIAL_STATE, projectId: initialProjectId });
  const [inspectionError, setInspectionError] = useState<string | null>(null);

  // Load legacy Script Hub modules from the Flask single-machine module catalog.
  const modulesState = useApi(() => listScriptHubModules(), []);
  const availableModules = modulesState.status === "ready" ? modulesState.data.modules : [];

  const completedSteps: number[] = [];
  if (wizard.pepPaths.length > 0 || wizard.profilePath || wizard.transcriptomePath)
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
    (data: { projectId: string; assetSetName: string; pepPaths: string[]; profilePath: string; transcriptomePath: string }) => {
      setWizard((prev) => ({
        ...prev,
        projectId: data.projectId,
        assetSetName: data.assetSetName,
        pepPaths: data.pepPaths,
        profilePath: data.profilePath,
        transcriptomePath: data.transcriptomePath,
        inspection: null,
        selectedModules: [],
        moduleConfigs: {},
        jobIds: [],
        resultsByJobId: {},
      }));
      setInspectionError(null);
    },
    [],
  );

  const handleInspect = useCallback(async () => {
    setInspectionError(null);
    try {
      const data = await inspectScriptHubDataSelection({
        project_id: wizard.projectId || undefined,
        pep_paths: wizard.pepPaths,
        profile_path: wizard.profilePath || undefined,
        transcriptome_path: wizard.transcriptomePath || undefined,
      });

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
      const profilePreview = profilePreviewResult.status === "fulfilled"
        ? tablePreviewFromResponse(profilePreviewResult.value)
        : undefined;
      const pepPreview = pepPreviewResult.status === "fulfilled"
        ? tablePreviewFromResponse(pepPreviewResult.value)
        : undefined;

      if (profilePreviewResult.status === "rejected") {
        previewWarnings.push(`Profile preview failed: ${profilePreviewResult.reason instanceof Error ? profilePreviewResult.reason.message : "unable to read table"}`);
      }
      if (pepPreviewResult.status === "rejected") {
        previewWarnings.push(`PEP preview failed: ${pepPreviewResult.reason instanceof Error ? pepPreviewResult.reason.message : "unable to read table"}`);
      }

      const inspection: InspectionResult = {
        samples: Number(data.sample_count || 0),
        sampleNames,
        chains: Number(data.chain_count ?? chains.length),
        chainLabels: chains,
        pepFiles: Number(data.pep_file_count || 0),
        profileLoaded: Boolean(data.profile_path || profileColumns.length > 0),
        transcriptomeLoaded: Boolean(data.transcriptome_path || wizard.transcriptomePath),
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
        inspection,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Source inspection failed";
      setInspectionError(message);
    }
  }, [wizard.projectId, wizard.pepPaths, wizard.profilePath, wizard.transcriptomePath]);

  const handleModuleUpdate = useCallback(
    (selectedModules: string[], moduleConfigs: Record<string, Record<string, unknown>>) => {
      setWizard((prev) => ({
        ...prev,
        selectedModules,
        moduleConfigs,
        jobIds: [],
        resultsByJobId: {},
      }));
    },
    [],
  );

  const handleJobsCreated = useCallback((jobIds: string[]) => {
    setWizard((prev) => ({ ...prev, jobIds }));
  }, []);

  const handleComplete = useCallback((resultsByJobId: Record<string, JobResultsResponse>) => {
    setWizard((prev) => ({ ...prev, resultsByJobId }));
  }, []);

  const handleReset = useCallback(() => {
    setWizard((prev) => ({
        ...prev,
        stage: 1,
        assetSetName: "",
        pepPaths: [],
        profilePath: "",
        transcriptomePath: "",
        inspection: null,
      selectedModules: [],
      moduleConfigs: {},
      jobIds: [],
      resultsByJobId: {},
    }));
  }, []);

  const sourceContext = wizard.inspection
    ? {
        projectId: wizard.projectId,
        assetSetId: wizard.assetSetName,
        profilePath: wizard.profilePath,
        pepPaths: wizard.pepPaths,
        transcriptomePath: wizard.transcriptomePath,
        chains: wizard.inspection.chainLabels,
        sampleNames: wizard.inspection.sampleNames,
        profileFields: wizard.inspection.profileFields,
        groupFields: wizard.inspection.groupFields,
        pepColumns: wizard.inspection.pepColumns,
        profilePreview: wizard.inspection.profilePreview,
        pepPreview: wizard.inspection.pepPreview,
      }
    : undefined;

  /* ── Validation ── */
  const canProceed = () => {
    const s = wizard.stage;
    if (s === 1)
      return (
        wizard.projectId &&
        (wizard.pepPaths.length > 0 || !!wizard.profilePath || !!wizard.transcriptomePath)
      );
    if (s === 2) return !!wizard.inspection && hasAnySelectableModule(availableModules, sourceContext);
    if (s === 3) {
      return wizard.selectedModules.length > 0 && wizard.selectedModules.every((key) => {
        const selected = availableModules.find((module) => module.key === key);
        return isModuleSelectable(selected, sourceContext);
      });
    }
    if (s === 4) return wizard.jobIds.length > 0;
    if (s === 5) return Object.keys(wizard.resultsByJobId).length > 0;
    return true; // stage 6 always can proceed (it's the end)
  };

  const stageGateMessage = (() => {
    if (wizard.stage !== 2 || !wizard.inspection) return "";
    if (hasAnySelectableModule(availableModules, sourceContext)) return "";
    return "No analysis module can run with the current asset set. Please add PEP, Profile, or Transcriptome data before entering module configuration.";
  })();

  /* ── Build stepper steps ── */
  const stepperSteps: StepDef[] = WIZARD_STEPS.map((label) => ({ label }));

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
        title="Script Hub Wizard"
        subtitle={`Stage ${wizard.stage} of ${WIZARD_STEPS.length} — ${WIZARD_STEPS[wizard.stage - 1]}`}
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
          Project: {wizard.projectId ? wizard.projectId.slice(0, 8) : "none"}
        </span>
      </PageHeader>

      {/* Stepper */}
      <Stepper steps={stepperSteps} currentStep={wizard.stage - 1} />

      {/* Stage Content */}
      <div style={{ minHeight: "400px" }}>
        {wizard.stage === 1 && (
          <Stage1DataIntake
            projectId={wizard.projectId}
            pepPaths={wizard.pepPaths}
            profilePath={wizard.profilePath}
            transcriptomePath={wizard.transcriptomePath}
            onUpdate={handleDataUpdate}
          />
        )}

        {wizard.stage === 2 && (
          <Stage2SourceInspection
            pepPaths={wizard.pepPaths}
            profilePath={wizard.profilePath}
            transcriptomePath={wizard.transcriptomePath}
            inspection={wizard.inspection}
            inspectionError={inspectionError}
            onInspect={handleInspect}
          />
        )}

        {wizard.stage === 3 && (
          <Stage3ModuleConfig
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
            }}
            moduleConfigs={wizard.moduleConfigs}
            jobIds={wizard.jobIds}
            onJobsCreated={handleJobsCreated}
            onComplete={handleComplete}
          />
        )}

        {wizard.stage === 5 && (
          <Stage5Results
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
          disabled={isFirstStage}
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
          Back
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
            Next
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
            Start New Analysis
          </button>
        )}
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
