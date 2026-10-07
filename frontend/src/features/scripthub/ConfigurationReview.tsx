import type { ConfigurationReviewItem } from "./configurationValidation";
import "./ConfigurationReview.css";

export function ConfigurationReview({items, onConfigure}:{items:ConfigurationReviewItem[]; onConfigure:(module:string)=>void}) {
  if (!items.length) return null;
  const pending=items.filter(item=>item.issue);
  return <section aria-label="运行前参数检查" className="configuration-review">
    <div className="configuration-review__header">
      <strong>{pending.length ? `还有 ${pending.length} 项分析需要补充参数` : "必要参数已填写"}</strong>
      <p>{pending.length ? "补充下方参数后，再进入运行步骤。" : "输入检查通过后，可进入运行步骤确认任务和结果来源。"}</p>
    </div>
    <ul className="configuration-review__items">
      {items.map(item=><li key={item.module} className={item.issue ? "configuration-review__item configuration-review__item--pending" : "configuration-review__item"}>
        <div><strong>{item.label}</strong><p>{item.issue || "已填写必要参数"}</p>{item.possibleSource && <p className="configuration-review__source">运行步骤可选择复用「{item.possibleSource}」的结果。</p>}</div>
        <button type="button" className="btn btn-secondary" onClick={()=>onConfigure(item.module)} aria-label={`${item.issue ? "补充参数" : "查看参数"}：${item.label}`}>{item.issue ? "补充参数" : "查看参数"}</button>
      </li>)}
    </ul>
  </section>;
}
