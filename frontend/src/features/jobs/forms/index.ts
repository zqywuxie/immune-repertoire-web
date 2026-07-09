/**
 * ui_entry → form component mapping.
 *
 * Each form receives the same props:
 *   - projectId: string
 *   - groupSpecs: GroupSpec[]        (where applicable)
 *   - loadingSpecs: boolean
 *   - value: Record<string, unknown>  (current payload)
 *   - onChange: (v: Record<string, unknown>) => void
 *
 * Forms that don't need groupSpecs (ImageSelectionForm, ComparisonConfigForm,
 * PipelineConfigForm) receive the props anyway for consistency; they simply
 * ignore the ones they don't use.
 */
export { ChartsCombinedForm } from "./ChartsCombinedForm";
export { SimpleForm } from "./SimpleForm";
export { MultiSelectForm } from "./MultiSelectForm";
export { ImageSelectionForm } from "./ImageSelectionForm";
export { ComparisonConfigForm } from "./ComparisonConfigForm";
export { PipelineConfigForm } from "./PipelineConfigForm";
export { LegacyScriptHubForm } from "./LegacyScriptHubForm";
export { DbAlignmentConfig as ScriptHubDbAlignmentConfig } from "../../scripthub/modules/DbAlignmentConfig";
export { ProfileConfig as ScriptHubProfileConfig } from "../../scripthub/modules/ProfileConfig";
export { PepAnalysisConfig as ScriptHubPepAnalysisConfig } from "../../scripthub/modules/PepAnalysisConfig";
export { PgenAnalysisConfig as ScriptHubPgenAnalysisConfig } from "../../scripthub/modules/PgenAnalysisConfig";
export { TopCloneConfig as ScriptHubTopCloneConfig } from "../../scripthub/modules/TopCloneConfig";
export { UmapConfig as ScriptHubUmapConfig } from "../../scripthub/modules/UmapConfig";
export { VolcanoConfig as ScriptHubVolcanoConfig } from "../../scripthub/modules/VolcanoConfig";
export { GoKeggConfig as ScriptHubGoKeggConfig } from "../../scripthub/modules/GoKeggConfig";
export { UmapinConfig as ScriptHubUmapinConfig } from "../../scripthub/modules/UmapinConfig";
export { MlAnalysisConfig as ScriptHubMlAnalysisConfig } from "../../scripthub/modules/MlAnalysisConfig";
export { MaitNktConfig as ScriptHubMaitNktConfig } from "../../scripthub/modules/MaitNktConfig";

import type { GroupSpec } from "../../../shared/api/groupSpecs";
import type { ComponentType } from "react";
import type { TablePreview } from "../../scripthub/stages/Stage2SourceInspection";
import { ChartsCombinedForm } from "./ChartsCombinedForm";
import { SimpleForm } from "./SimpleForm";
import { MultiSelectForm } from "./MultiSelectForm";
import { ImageSelectionForm } from "./ImageSelectionForm";
import { ComparisonConfigForm } from "./ComparisonConfigForm";
import { PipelineConfigForm } from "./PipelineConfigForm";
import { LegacyScriptHubForm } from "./LegacyScriptHubForm";
import { DbAlignmentConfig as ScriptHubDbAlignmentConfig } from "../../scripthub/modules/DbAlignmentConfig";
import { ProfileConfig as ScriptHubProfileConfig } from "../../scripthub/modules/ProfileConfig";
import { PepAnalysisConfig as ScriptHubPepAnalysisConfig } from "../../scripthub/modules/PepAnalysisConfig";
import { PgenAnalysisConfig as ScriptHubPgenAnalysisConfig } from "../../scripthub/modules/PgenAnalysisConfig";
import { TopCloneConfig as ScriptHubTopCloneConfig } from "../../scripthub/modules/TopCloneConfig";
import { UmapConfig as ScriptHubUmapConfig } from "../../scripthub/modules/UmapConfig";
import { VolcanoConfig as ScriptHubVolcanoConfig } from "../../scripthub/modules/VolcanoConfig";
import { GoKeggConfig as ScriptHubGoKeggConfig } from "../../scripthub/modules/GoKeggConfig";
import { UmapinConfig as ScriptHubUmapinConfig } from "../../scripthub/modules/UmapinConfig";
import { MlAnalysisConfig as ScriptHubMlAnalysisConfig } from "../../scripthub/modules/MlAnalysisConfig";
import { MaitNktConfig as ScriptHubMaitNktConfig } from "../../scripthub/modules/MaitNktConfig";

export type ModuleFormProps = {
  projectId: string;
  module: string;
  sourceContext?: ScriptHubSourceContext;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

export type ScriptHubSourceContext = {
  projectId?: string;
  assetSetId?: string;
  profilePath?: string;
  pepPaths?: string[];
  transcriptomePath?: string;
  sampleNames: string[];
  chains: string[];
  profileFields: string[];
  groupFields: string[];
  pepColumns: string[];
  profilePreview?: TablePreview;
  pepPreview?: TablePreview;
};

export type ModuleFormComponent = ComponentType<ModuleFormProps>;

/** Map from manifest ``ui_entry`` to the React component that renders it. */
export const FORM_REGISTRY: Record<string, ModuleFormComponent> = {
  ChartsCombinedForm,
  SimpleForm,
  MultiSelectForm,
  ImageSelectionForm,
  ComparisonConfigForm,
  PipelineConfigForm,
  LegacyScriptHubForm,
  ScriptHubDbAlignmentConfig,
  ScriptHubProfileConfig,
  ScriptHubPepAnalysisConfig,
  ScriptHubPgenAnalysisConfig,
  ScriptHubTopCloneConfig,
  ScriptHubUmapConfig,
  ScriptHubVolcanoConfig,
  ScriptHubGoKeggConfig,
  ScriptHubUmapinConfig,
  ScriptHubMlAnalysisConfig,
  ScriptHubMaitNktConfig,
};

export function getFormComponent(uiEntry: string): ModuleFormComponent | null {
  return FORM_REGISTRY[uiEntry] || null;
}
