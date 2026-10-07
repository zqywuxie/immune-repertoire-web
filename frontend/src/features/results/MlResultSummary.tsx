import {useEffect,useId,useState} from "react";
import "./MlResultSummary.css";

type RecordData=Record<string,unknown>;
type Props={storageKey?:string;metadata:unknown;availableFiles:string[];onOpenFile:(name:string)=>void};
const record=(value:unknown):RecordData=>value&&typeof value==="object"&&!Array.isArray(value)?value as RecordData:{};
const modelLabels:Record<string,string>={logistic_l1:"逻辑回归（L1）",random_forest:"随机森林",extra_trees:"极端随机树",logistic_l2:"逻辑回归（L2）",gaussian_nb:"高斯朴素贝叶斯",knn:"K 近邻",rbf_svm:"径向基 SVM",linear_svm:"线性 SVM",gradient_boosting:"梯度提升树",xgboost:"XGBoost"};
const fields=[["nested_cv_mean_accuracy","各折平均准确率"],["nested_cv_mean_balanced_accuracy","各折平均平衡准确率"],["nested_cv_mean_macro_f1","各折平均宏平均 F1"],["roc_auc","ROC AUC"],["average_precision","平均精确率"]] as const;
function savedNumber(value:unknown){
 if(typeof value==="number"&&Number.isFinite(value))return String(value);
 if(typeof value==="string"&&value.trim()&&Number.isFinite(Number(value)))return value;
 return "未记录";
}
function modelName(row:RecordData){return modelLabels[String(row.model_key||"")]||String(row.model_label||row.model_key||"未记录模型");}
function evaluationName(value:unknown){
 if(value==="nested_stratified_group_k_fold")return "受试者分组嵌套交叉验证";
 if(value==="nested_stratified_k_fold")return "样本分层嵌套交叉验证";
 return value?"其他已保存评估方式":"未记录评估方式";
}

function storedSelection(key?:string){
 try{return key?JSON.parse(sessionStorage.getItem(key)||"null"):{}}catch{return {}}
}

export function MlResultSummary({storageKey,metadata,availableFiles,onOpenFile}:Props){
 const data=record(metadata),id=useId();
 const [selected,setSelected]=useState(()=>String(storedSelection(storageKey)?.model||"")),[comparing,setComparing]=useState(()=>storedSelection(storageKey)?.comparing===true);
 useEffect(()=>{if(storageKey)try{sessionStorage.setItem(storageKey,JSON.stringify({model:selected,comparing}));}catch{/* Browsing remains available without storage. */}},[storageKey,selected,comparing]);
 const rawRows=Array.isArray(data.models)&&data.models.length?data.models:Array.isArray(data.model_results)&&data.model_results.length?data.model_results:[];
 const rows=rawRows.map(record).filter(row=>Object.keys(row).length);
 // Historical top-level metrics describe one model, never every selected model.
 if(!rows.length&&fields.some(([field])=>data[field]!==undefined))rows.push(data);
 if(!rows.length)return null;
 const occurrences=new Map<string,number>();
 const choices=rows.map(row=>{const name=String(row.model_key||row.model_label||"model"),count=occurrences.get(name)||0;occurrences.set(name,count+1);return {key:name+":"+count,row};});
 const active=choices.find(choice=>choice.key===selected)||choices[0],model=active.row;
 const knownNested=["nested_stratified_group_k_fold","nested_stratified_k_fold"].includes(String(model.evaluation_method||""));
 const stability=record(data.stability_selection);
 const mode={profile:"样本指标",vj:"V/J 特征",profile_vj:"联合特征"}[String(data.data_mode||data.mode||"") as "profile"]||"未记录";
 const fileButton=(name:string,label:string)=>availableFiles.includes(name)?<button type="button" className="btn btn-secondary" onClick={()=>onOpenFile(name)}>{label}</button>:null;
 return <section className="ml-result-summary" aria-label="机器学习结果概览">
  <div className="ml-result-summary-heading"><div><span className="ml-result-eyebrow">机器学习 · 保存结果</span><h4>模型评估与稳定特征</h4></div><span className="ml-result-model-count">{rows.length} 个模型</span></div>
  <dl className="ml-result-context">
   <div><dt>实际纳入样本</dt><dd>{savedNumber(data.samples)}</dd></div>
   <div><dt>输入特征数</dt><dd>{savedNumber(data.raw_feature_number)}</dd></div>
   <div><dt>数据模式</dt><dd>{mode}</dd></div>
   <div><dt>分类标签列</dt><dd>{typeof data.label_col==="string"&&data.label_col?data.label_col:"未记录"}</dd></div>
  </dl>
  <div className="ml-result-model-controls">
   <label>查看模型<select aria-label="查看模型评估" value={active.key} onChange={event=>setSelected(event.target.value)}>{choices.map(choice=><option key={choice.key} value={choice.key}>{modelName(choice.row)}</option>)}</select></label>
   {rows.length>1&&<button type="button" className="btn btn-secondary" aria-expanded={comparing} aria-controls={id+"-comparison"} onClick={()=>setComparing(value=>!value)}>{comparing?"收起模型比较":"比较所有模型"}</button>}
  </div>
  <p className="ml-result-method"><strong>{evaluationName(model.evaluation_method)}</strong>{knownNested?" · 以下分数来自外层留出预测；模型参数在训练折内调优。":" · 以下仅展示已有记录，不补算或推测评估方式。"}</p>
  <dl className="ml-result-metrics" aria-label={modelName(model)+"保存指标"}>{fields.map(([key,label])=><div key={key}><dt>{knownNested&&["roc_auc","average_precision"].includes(key)?"折外 "+label:label}</dt><dd>{savedNumber(model[key])}</dd></div>)}</dl>
  <p className="ml-result-notes">外层折数：{savedNumber(model.nested_cv_outer_folds)}；最终模型特征数：{savedNumber(model.selected_feature_number)}。{model.std_cv_accuracy!==undefined&&<>各折准确率标准差：{savedNumber(model.std_cv_accuracy)}。</>}</p>
  {comparing&&<div id={id+"-comparison"} className="ml-result-comparison" tabIndex={0} role="region" aria-label="已保存模型指标比较">
   <table><caption>按保存顺序比较原始分数；未记录的指标不补零。评估方式见对应模型详情。</caption><thead><tr><th scope="col">模型</th>{fields.map(([key,label])=><th key={key} scope="col">{label}</th>)}</tr></thead><tbody>{choices.map(choice=><tr key={choice.key} data-selected={choice.key===active.key}><th scope="row">{modelName(choice.row)}</th>{fields.map(([key])=><td key={key}>{savedNumber(choice.row[key])}</td>)}</tr>)}</tbody></table>
  </div>}
  {Object.keys(stability).length>0&&<div className="ml-result-stability">
   <h5>{stability.enabled===true?"最终模型的稳定特征":stability.enabled===false?"本次未启用稳定特征筛选":"稳定特征筛选记录"}</h5>
   {stability.enabled===true&&<><p>筛选折数：{savedNumber(stability.folds)}；入选频率阈值：{savedNumber(stability.frequency_threshold)}；每模态最少保留：{savedNumber(stability.min_features_per_modality)}。</p>
    {Array.isArray(stability.selected_features)&&<p>最终稳定集合：{stability.selected_features.length} 项特征。</p>}
    {knownNested&&<p className="ml-result-notes">稳定集合用于全样本最终模型重训；外层留出评估使用各训练折独立筛选的特征，不使用全样本稳定集合计算评估分数。</p>}
   </>}
  </div>}
  <div className="ml-result-file-actions">{fileButton("model_comparison.csv","查看模型比较表")}{fileButton("feature_stability.csv","查看特征稳定性表")}{fileButton("stable_features.csv","查看最终稳定特征表")}</div>
  {Object.keys(record(model.final_model_params||model.best_params)).length>0&&<details className="ml-result-parameters"><summary>查看最终全样本模型参数</summary><pre>{JSON.stringify(model.final_model_params||model.best_params,null,2)}</pre></details>}
 </section>;
}
