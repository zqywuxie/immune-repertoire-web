import { useEffect, useState } from "react";
import { assetLabel, type RequiredAsset } from "./moduleRequirements";
import { Stage2SourceInspection, type InspectionResult } from "./stages/Stage2SourceInspection";
import "./AnalysisInputReview.css";

type Props = {
  projectId: string; assetSet: string; inputTypes: RequiredAsset[];
  inspection: InspectionResult | null; inspecting: boolean; inspectionError: string | null;
  validationPending: boolean; needsMapping: boolean; alignmentMismatch: boolean; alignmentReviewed: boolean;
  onAlignmentReviewed: (reviewed: boolean) => void;
  onInspect: (mappingChanged?: boolean) => Promise<void>;
  onChangeData: () => void;
  pepPaths: string[]; profilePath: string; transcriptomePath: string; deconvolutionPath?: string;
};

export function AnalysisInputReview(props: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasErrors = Boolean(props.inspection?.inputQuality?.errors.some(message => !message.includes("后台校验")));
  const hasIssues = Boolean(props.inspectionError || hasErrors || props.needsMapping || (props.alignmentMismatch && !props.alignmentReviewed));
  useEffect(() => { if (hasIssues) setExpanded(true); }, [hasIssues]);
  const status = props.inspectionError ? "本次输入需要处理"
    : props.inspecting ? "正在检查本次输入"
    : props.validationPending ? "数据正在后台校验"
    : hasErrors || props.needsMapping ? "本次输入需要处理"
    : props.alignmentMismatch && !props.alignmentReviewed ? "请确认样本匹配范围"
    : props.inputTypes.length === 0 ? "核对前置结果" : "本次输入已核验";
  const sampleCounts = (props.inspection?.inputQuality?.inputs || []).filter(input => input.status === "checked")
    .map(input => `${input.label || assetLabel(input.kind as RequiredAsset)} ${input.sample_count} 个样本`).join(" · ");
  return <section aria-label="本次分析数据" className="analysis-input-review">
    <div className="analysis-input-review__summary">
      <div>
        <strong>{props.assetSet} · {status}</strong>
        <p>{props.inputTypes.length ? `核验范围：${props.inputTypes.map(assetLabel).join("、")}${props.inputTypes.length === 1 && props.inspection?.samples ? ` · ${props.inspection.samples} 个样本` : ""}` : "前置结果的来源与样本范围将在下方核对"}</p>
        {props.inputTypes.length > 1 && sampleCounts && <p>{sampleCounts}</p>}
        {props.inputTypes.length > 1 && props.inspection?.alignmentGroups?.length === 0 && <p>独立分析按各自样本范围运行。</p>}
      </div>
      <div className="analysis-input-review__actions">
        <button type="button" className="btn btn-secondary" aria-expanded={expanded} onClick={() => setExpanded(previous => !previous)}>{expanded ? "收起输入检查" : "查看输入检查"}</button>
        <button type="button" className="btn btn-secondary" onClick={props.onChangeData}>更换或检查数据</button>
      </div>
    </div>
    {props.inspectionError && !expanded && <p role="alert">{props.inspectionError}</p>}
    {expanded && <div className="analysis-input-review__details">
      <Stage2SourceInspection projectId={props.projectId} assetSet={props.assetSet} inputTypes={props.inputTypes}
        pepPaths={props.inputTypes.includes("pep") ? props.pepPaths : []}
        profilePath={props.inputTypes.includes("profile") ? props.profilePath : ""}
        transcriptomePath={props.inputTypes.includes("transcriptome") ? props.transcriptomePath : ""}
        deconvolutionPath={props.inputTypes.includes("deconvolution") ? props.deconvolutionPath : ""}
        inspection={props.inspection} inspectionError={props.inspectionError} inspecting={props.inspecting} onInspect={props.onInspect}/>
      {props.alignmentMismatch && <label className="analysis-input-review__alignment"><input type="checkbox" checked={props.alignmentReviewed} onChange={event => props.onAlignmentReviewed(event.target.checked)}/>我已核对样本匹配情况，了解各模块将按其要求使用对应样本；本操作不自动合并或删除样本。</label>}
    </div>}
  </section>;
}
