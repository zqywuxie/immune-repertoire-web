import { useAnalysisData } from "./AnalysisDataContext";

export function AnalysisSelectionNotice({projectId,dataset,onClear}:{projectId:string;dataset:string;onClear:()=>void}) {
  const {data,selectionState="ready",selectionError,retrySelection}=useAnalysisData();
  if(data?.projectId!==projectId || data.assetSetName!==dataset || selectionState==="ready")return null;
  return <aside className="data-input-intent" aria-label="恢复本次输入">
    {selectionState==="loading"?<p role="status">正在核对上次选择的全部输入与版本…</p>:<><p className="data-error" role="alert">本次输入暂时无法完整恢复：{selectionError}</p><p className="data-muted">请重试或重新选择输入。</p><div className="data-row-actions"><button className="btn btn-secondary" onClick={retrySelection}>重试恢复输入</button><button className="btn btn-secondary" onClick={onClear}>重新选择输入</button></div></>}
  </aside>;
}
