import { MoreHorizontal, FileSearch } from "lucide-react";
import type { ProjectAsset } from "../../shared/types/domain";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { getAssetSetLabel, isInputAsset } from "./assetSets";
import { assetTypeLabels, validationLabels } from "./assetLabels";

export function AssetMobileList({ assets, selected, allSelected, loading, busy, showSelect, showGroup, showStatus,
  selectionLimit, name, formatSize, onToggleAll, onToggle, onView, onActions, emptyLabel }: {
  selectionLimit?: number; assets: ProjectAsset[]; selected: Set<string>; allSelected: boolean; loading: boolean; busy: boolean;
  showSelect: boolean; showGroup: boolean; showStatus: boolean; emptyLabel: string;
  name: (asset: ProjectAsset) => string; formatSize: (size: number) => string;
  onToggleAll: () => void; onToggle: (id: string) => void; onView: (asset: ProjectAsset) => void; onActions: (asset: ProjectAsset) => void;
}) {
  return <div className="data-mobile-records" aria-label="文件记录">
    {showSelect && <label className="data-mobile-select-all"><input type="checkbox" aria-label="选择当前列表全部文件"
      checked={allSelected} ref={node=>{if(node)node.indeterminate=!allSelected && assets.some(asset=>selected.has(asset.id));}} disabled={busy || !assets.length || (!!selectionLimit && selected.size>=selectionLimit && !allSelected)} onChange={onToggleAll} />选择本页文件</label>}
    {loading ? <p role="status">正在读取文件…</p> : !assets.length ? <p className="data-table-empty">{emptyLabel}</p> : assets.map(asset => {
      const info = asset.metadata || {}; const validation = info.validation as {status?: string} | undefined;
      return <article className={`data-mobile-record${selected.has(asset.id) ? " is-selected" : ""}`} key={asset.id} aria-label={`文件 ${name(asset)}`}>
        <div className="data-mobile-file-heading">
          {showSelect && <input type="checkbox" aria-label={`选择 ${name(asset)}`} checked={selected.has(asset.id)} disabled={busy || (!!selectionLimit && selected.size>=selectionLimit && !selected.has(asset.id))} onChange={() => onToggle(asset.id)} />}
          <button className="data-mobile-file-name" aria-label={`查看 ${name(asset)}`} title={name(asset)} onClick={() => onView(asset)}><FileSearch size={17} /><span>{name(asset)}</span></button>
          <button className="data-mobile-more" aria-label={`更多操作：${name(asset)}`} onClick={() => onActions(asset)}><MoreHorizontal size={20} /></button>
        </div>
        {Boolean(info.description) && <p className="data-file-description" title={String(info.description)}>{String(info.description).slice(0,100)}{String(info.description).length>100?"…":""}</p>}
        <div className="data-mobile-record-meta"><span>{assetTypeLabels[asset.asset_type] || "其他文件"}</span>{showGroup && <span>数据集：{getAssetSetLabel(asset)}</span>}{Boolean(info.superseded) && <span className="data-dataset-tag">历史版本</span>}</div>
        {(isInputAsset(asset) || showStatus) && <div>{isInputAsset(asset) ? <span className={`data-validation state-${validation?.status || "unknown"}`}>
          {validationLabels[validation?.status || "unknown"] || "尚未校验"}</span> : <StatusBadge status={String(info.status || info.job_status || "completed")} />}</div>}
        <p className="data-mobile-record-footer">{formatSize(asset.size)} · {asset.uploaded_at ? new Date(asset.uploaded_at).toLocaleString("zh-CN", {hour12:false}) : "上传时间未记录"}</p>
      </article>;
    })}
  </div>;
}
