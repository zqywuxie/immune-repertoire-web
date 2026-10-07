import type { JobSummary } from "../../shared/types/domain";
import { analysisLabel, analysisLabels } from "../../shared/utils/analysisLabels";
export type RecordValue = Record<string, unknown>;
export type ConfigRow = {label: string; value: unknown; options?: Record<string,string>};
export function objectValue(value: unknown): RecordValue {
 return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
}
export function jobSettings(payload: RecordValue) {
 // Normalized execution configuration takes precedence over the submitted values.
 return {...payload, ...objectValue(payload._module_config), ...objectValue(payload.config_json)};
}
const labels: Record<string,string> = {
 selected_chains:"受体链",chain:"受体链",group_field:"分组列",group_fields:"分组列",grouptype_fields:"分组列",
 sample_column:"样本列",label_column:"标签列",batch_field:"批次列",selected_samples:"指定样本",
 selected_expression_samples:"指定表达样本",selected_group_values:"指定分组",selected_expression_groups:"指定表达分组",
 selected_samples_by_group:"各组指定样本",group_order:"分组顺序",comparisons:"比较条件",
 param_begin:"指标起始列",param_over:"指标结束列",grouping_begin:"分组起始列",grouping_over:"分组结束列",
 classification_begin:"分类起始列",classification_over:"分类结束列",field_mapping:"字段映射",
 input_mode:"输入模式",analysis_mode:"分析模式",analysis_type:"分析类型",mode:"计算模式",selected_modules:"分析内容",
 top_n:"克隆数量",pvalue_threshold:"p 值阈值",pvalue_cutoff:"p 值阈值",qvalue_cutoff:"q 值阈值",
 logfc_cutoff:"表达差异阈值",min_sample_threshold:"最少样本数",optional_steps:"选定步骤",
 selected_categories:"分析类别",categories:"分析类别",pathology_values:"病理分类",contained_pathology:"包含病理分类",
 n_neighbors:"邻居数",min_dist:"最小距离",n_components:"降维维数",metric:"距离度量",random_state:"随机种子",
 n_permutations:"置换次数",seed:"随机种子",test_size:"测试集比例",cv_folds:"交叉验证折数",
 normalization:"归一化方式",group_prefix:"分组前缀",species:"物种",organism:"物种",databases:"数据库",
 subclass_measure:"亚类度量",csr_measure:"类别转换度量",measurement:"浸润数值含义",sample_id_mapping:"样本标识映射",
 paired_samples:"样本配对",sample_pairing:"样本配对",sample_keys:"指定样本标识",
};
const options: Record<string,Record<string,string>> = {
 input_mode:{expression:"转录组表达矩阵",usage:"基因使用频率",deg:"差异表达结果",profile:"样本指标表"},
 analysis_mode:{unified:"联合分析",profile:"样本指标分析",usage:"特征分析"},
 analysis_type:{composition:"链与亚类构成",csr:"类别转换矩阵",igh_subclass_topclone:"IGH 亚类优势克隆"},
 normalization:{none:"不归一化",zscore:"标准化",relative:"相对比例"},
 metric:{euclidean:"欧氏距离",cosine:"余弦距离",correlation:"相关距离",manhattan:"曼哈顿距离"},
 species:{human:"人",mouse:"小鼠"},organism:{human:"人",mouse:"小鼠"},
 subclass_measure:{reads:"读段数",cdr3:"克隆数"},csr_measure:{auto:"自动识别",CSR_ratio:"CSR_ratio",CSR1:"CSR1",CSR0:"CSR0"},
 selected_modules:{heatmap:"热力图",treemap:"克隆分布树图",chord:"V/J 基因配对"},
};
const scopeKeys = new Set(["selected_chains","chain","group_field","group_fields","grouptype_fields","sample_column","label_column","batch_field","selected_samples","selected_expression_samples","selected_group_values","selected_expression_groups","selected_samples_by_group","group_order","comparisons","param_begin","param_over","grouping_begin","grouping_over","classification_begin","classification_over","field_mapping","sample_id_mapping","paired_samples","sample_pairing","sample_keys"]);
export function configurationRows(settings: RecordValue, scope: boolean): ConfigRow[] {
 return Object.entries(labels).filter(([key])=>scopeKeys.has(key)===scope && Object.hasOwn(settings,key) && settings[key]!==null && settings[key]!==undefined)
 .map(([key,label])=>({label,value:settings[key],options:key==="selected_modules" ? {...analysisLabels, ...options[key]} : options[key]}));
}
const inputTypes: Record<string,string> = {
 pep:"克隆序列表",profile:"样本指标与分组表",datapoint:"样本指标与分组表",transcriptome:"转录组表达矩阵",
 deconvolution:"免疫浸润结果",cibersort:"免疫浸润结果",cached_usage:"前置特征结果",vj_usage:"前置基因使用结果",
 cached_pep:"前置克隆结果",deg:"前置差异表达结果",
};
export type InputSummary = {label: string; name: string; path?: string; id?: string; version?: string; dataset?: string};
function fileName(value: string) {return value.split(/[\\/]/).filter(Boolean).at(-1) || value;}
export function jobInputs(payload: RecordValue): InputSummary[] {
 const recorded=Array.isArray(payload.input_assets) ? payload.input_assets.filter(value=>value&&typeof value==="object").map(value=>{
  const item=objectValue(value),type=String(item.asset_type||item.kind||"");
  const path=String(item.path||item.storage_path||"");
  const name=String(item.original_name||item.filename||item.name||fileName(path)||item.asset_id||"未记录文件名");
  return {label:inputTypes[type]||"输入数据",name,path:path||undefined,id:item.asset_id?String(item.asset_id):undefined,version:typeof item.content_version==="string"?item.content_version:undefined,dataset:typeof item.asset_set==="string"?item.asset_set:undefined};
 }) : [];
 if(recorded.length)return recorded;
 const result: InputSummary[]=[];
 for(const [key,label] of [["pep_paths","克隆序列表"],["pep_path","克隆序列表"],["profile_path","样本指标与分组表"],["datapoint_path","样本指标与分组表"],["transcriptome_path","转录组表达矩阵"],["expression_path","转录组表达矩阵"],["deconvolution_path","免疫浸润结果"],["data_dir","前置特征目录"]] as const){
  const values=Array.isArray(payload[key])?payload[key] as unknown[]:[payload[key]];
  for(const value of values)if(typeof value==="string"&&value.trim()&&!result.some(item=>item.path===value))result.push({label,name:fileName(value),path:value});
 }
 if(!result.length&&payload.file_id)result.push({label:"输入文件标识",name:String(payload.file_id),id:String(payload.file_id)});
 return result;
}
export function taskName(job: JobSummary) {
 const payload=objectValue(job.payload);
 const name=payload._task_name||payload.task_name||payload.output_name;
 return typeof name==="string"&&name ? name : analysisLabel(job.module);
}
