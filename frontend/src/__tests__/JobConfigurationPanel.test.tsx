import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { JobConfigurationPanel } from "../features/jobs/JobConfigurationPanel";
import type { JobSummary } from "../shared/types/domain";
const job=(payload:Record<string,unknown>,extra:Partial<JobSummary>={})=>({id:"config-job",module:"volcano",status:"completed",payload,...extra}) as JobSummary;
afterEach(cleanup);
it("规范化执行条件优先，保留零值和关闭状态，不补当前默认参数",()=>{
 render(<JobConfigurationPanel job={job({pvalue_threshold:0.05,_module_config:{pvalue_threshold:0.02},config_json:{pvalue_threshold:0,contained_pathology:false,logfc_cutoff:0,input_mode:"expression"}})}/>);
 expect(screen.getByText("转录组表达矩阵")).toBeVisible();expect(screen.getAllByText("0")).toHaveLength(2);expect(screen.getByText("否")).toBeVisible();
 expect(screen.queryByText("邻居数")).toBeNull();expect(screen.queryByText("0.05")).toBeNull();expect(screen.queryByText("0.02")).toBeNull();
});
it("实际输入显示文件名，技术路径默认折叠，前置任务链接来自保存引用",()=>{
 const payload={_task_name:"病例组差异",asset_set:"数据集 二",input_assets:[{asset_type:"transcriptome",path:"/storage/输入 数据/表达矩阵.csv",asset_id:"input-1"},{asset_type:"profile",path:"C:\\旧目录\\分组表.tsv"}],
 upstream_input:{source_job_id:"job/source?x=1",artifact_id:"artifact-1",module:"pep-analysis"},config_json:{comparisons:[{group1:"病例组 / A",group2:"对照组 B"}],selected_samples:["001","010"]}};
 const original=JSON.stringify(payload);
 render(<JobConfigurationPanel job={job(payload,{project_id:"项目 1"})}/>);
 expect(screen.getByText("表达矩阵.csv")).toBeVisible();expect(screen.getByText("分组表.tsv")).toBeVisible();expect(screen.getByText("数据集 二")).toBeVisible();
 expect(screen.getByText("前组：病例组 / A；后组：对照组 B")).toBeVisible();expect(screen.getByText("001")).toBeVisible();
 expect(screen.getByRole("link",{name:"查看来源任务"})).toHaveAttribute("href","/analysis/script-hub/jobs?job=job%2Fsource%3Fx%3D1");
 expect(screen.getByRole("link",{name:"查看项目"})).toHaveAttribute("href","/management/projects/%E9%A1%B9%E7%9B%AE%201");
 const raw=screen.getByText(/"input-1"/);expect(raw).not.toBeVisible();
 fireEvent.click(screen.getByText("完整技术参数"));expect(raw).toBeVisible();expect(JSON.stringify(payload)).toBe(original);
});
it("历史未知参数与缺失来源明确展示，不虚构默认数据集或文件可用状态",()=>{
 render(<JobConfigurationPanel job={job({future_parameter:"preserve-original",upstream_artifact_id:"old-artifact"})}/>);
 expect(screen.getByText("未记录数据集")).toBeVisible();expect(screen.getByText("未记录项目")).toBeVisible();
 expect(screen.getByText("未记录来源任务")).toBeVisible();expect(screen.getByText(/不代表文件当前仍可用/)).toBeVisible();
 expect(screen.queryByRole("link",{name:"查看来源任务"})).toBeNull();
 expect(screen.getByText(/preserve-original/)).not.toBeVisible();fireEvent.click(screen.getByText("完整技术参数"));expect(screen.getByText(/preserve-original/)).toBeVisible();
});
it("大量样本默认只挂载前8项，用户展开后可核对完整标识并收起",()=>{
 const samples=Array.from({length:2000},(_,index)=>"样本-"+String(index).padStart(4,"0"));
 render(<JobConfigurationPanel job={job({selected_samples:samples})}/>);
 expect(screen.getByText("已记录 2000 项")).toBeVisible();expect(screen.getByText("样本-0007")).toBeVisible();expect(screen.queryByText("样本-1999")).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:"查看完整名单"}));expect(screen.getByText("样本-1999")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"收起完整名单"}));expect(screen.queryByText("样本-1999")).toBeNull();
});
it("批次保留计划顺序和明确依赖，按各项输入展示，子任务链接不替换父任务",()=>{
 const items=[{module:"volcano",job_id:"child-1",status:"completed",payload:{input_mode:"expression",expression_path:"/storage/expression.csv"}},
 {module:"go-kegg-enrichment",status:"queued",depends_on:[0],upstream_from:0,payload:{input_mode:"deg",qvalue_cutoff:0.05}}];
 render(<JobConfigurationPanel job={job({items},{module:"analysis-batch"})}/>);
 expect(screen.getByText("批次计划（2 项）")).toBeVisible();expect(screen.getByText("依赖：第 1 项")).toBeVisible();expect(screen.getByText("使用第 1 项的分析产物")).toBeVisible();
 expect(screen.getByRole("link",{name:"查看子任务"})).toHaveAttribute("href","/analysis/script-hub/jobs?job=child-1");
 const second=screen.getAllByText("查看本项保存的条件")[1];fireEvent.click(second);expect(screen.getByText("差异表达结果")).toBeVisible();expect(screen.getByText("q 值阈值")).toBeVisible();
});
it("通用嵌套输入与字段映射保持科学列名和原始值",()=>{
 render(<JobConfigurationPanel job={job({_module_config:{pep_paths:["/storage/克隆表.csv"],selected_modules:["heatmap"],csr_measure:"CSR1",field_mapping:{cdr3_column:"CDR3_AA",copy_column:"counts"}}})}/>);
 expect(screen.getByText("克隆表.csv")).toBeVisible();expect(screen.getByText("热力图")).toBeVisible();expect(screen.getByText("CSR1")).toBeVisible();expect(screen.getByText("CDR3 列")).toBeVisible();expect(screen.getByText("CDR3_AA")).toBeVisible();
});


it("结果配置定位保存的旧文件与分组快照，不能用当前同名方案覆盖",()=>{
 const payload={asset_set:"甲",input_assets:[{asset_type:"profile",original_name:"同名.csv",asset_id:"old-file",asset_set:"甲",content_version:"saved-old"}],
  config_json:{group_spec_snapshot:{id:"spec-1",name:"执行时方案",project_id:"p1",asset_id:"old-spec-file",content_version:"saved-spec",group_order:["B","A"],spec_json:{source_asset_id:"old-file",asset_set:"甲",group_field:"治疗",groups:["B","A"]}}}};
 render(<JobConfigurationPanel job={job(payload,{project_id:"p1"})}/>);
 expect(screen.getByText("保存的版本：saved-old")).toBeVisible();
 const input=new URL(screen.getByRole("link",{name:"查看执行时的文件"}).getAttribute("href")!,"http://localhost");expect(input.searchParams.get("asset")).toBe("old-file");
 const snapshot=within(screen.getByRole("region",{name:"执行时的分组方案"}));expect(snapshot.getByText("saved-spec")).toBeVisible();expect(snapshot.getByText("治疗")).toBeVisible();
 expect(new URL(snapshot.getByRole("link",{name:"查看方案版本文件"}).getAttribute("href")!,"http://localhost").searchParams.get("asset")).toBe("old-spec-file");
 expect(snapshot.getByText("B").compareDocumentPosition(snapshot.getByText("A"))&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
