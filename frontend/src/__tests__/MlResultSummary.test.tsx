import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,within,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {MlResultSummary} from "../features/results/MlResultSummary";
import {JobResultPanel} from "../features/jobs/JobResultPanel";
import type {JobResultsResponse} from "../shared/api/jobs";
import {apiClient} from "../shared/api/client";

const first={model_key:"random_forest",nested_cv_mean_accuracy:0,nested_cv_mean_balanced_accuracy:0.1234567890123456,nested_cv_mean_macro_f1:0.4,roc_auc:0.6,average_precision:0.7,nested_cv_outer_folds:3,std_cv_accuracy:0,selected_feature_number:2,evaluation_method:"nested_stratified_group_k_fold",final_model_params:{depth:0,flag:false}};
const second={model_key:"gaussian_nb",nested_cv_mean_accuracy:0.8,roc_auc:"1.00000000001e-9",nested_cv_outer_folds:4,evaluation_method:"nested_stratified_k_fold",selected_feature_number:1};
const metadata={mode:"profile",samples:12,raw_feature_number:4,label_col:"类别 01",models:[first,second],nested_cv_mean_accuracy:1,stability_selection:{enabled:true,folds:3,frequency_threshold:0.6,min_features_per_modality:1,selected_features:["IGHG1","TRBV01"]}};
afterEach(()=>{cleanup();sessionStorage.clear();apiClient.invalidateCache();vi.restoreAllMocks();vi.unstubAllGlobals();});

it("展示保存指标的零值与原始精度，区分评估和全样本稳定集合",()=>{
 const original=JSON.stringify(metadata),open=vi.fn();
 render(<MlResultSummary metadata={metadata} availableFiles={["feature_stability.csv"]} onOpenFile={open}/>);
 expect(screen.getByLabelText("随机森林保存指标")).toHaveTextContent("0.1234567890123456");
 expect(screen.getByLabelText("随机森林保存指标").querySelector("dd")?.textContent).toBe("0");
 expect(screen.getByText("受试者分组嵌套交叉验证",{exact:true})).toBeInTheDocument();
 expect(screen.getByText(/外层留出评估使用各训练折独立筛选/)).toBeInTheDocument();
 expect(screen.getByText("最终稳定集合：2 项特征。",{exact:true})).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"查看特征稳定性表"}));expect(open).toHaveBeenCalledWith("feature_stability.csv");
 expect(screen.queryByRole("button",{name:"查看模型比较表"})).not.toBeInTheDocument();
 fireEvent.click(screen.getByText("查看最终全样本模型参数"));expect(screen.getByText(/"depth": 0/)).toHaveTextContent('"flag": false');
 expect(JSON.stringify(metadata)).toBe(original);
});

it("切换模型读取该模型的记录，刷新并改变保存顺序后保留选择",()=>{
 const view=render(<MlResultSummary metadata={metadata} availableFiles={[]} onOpenFile={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText("查看模型评估"),{target:{value:"gaussian_nb:0"}});
 const scores=screen.getByLabelText("高斯朴素贝叶斯保存指标");
 expect(scores).toHaveTextContent("0.8");expect(scores).toHaveTextContent("1.00000000001e-9");expect(scores).toHaveTextContent("未记录");
 expect(screen.getByText(/外层折数：4/)).toBeInTheDocument();
 view.rerender(<MlResultSummary metadata={{...metadata,models:[second,first]}} availableFiles={[]} onOpenFile={vi.fn()}/>);
 expect(screen.getByLabelText("查看模型评估")).toHaveValue("gaussian_nb:0");expect(screen.getByLabelText("高斯朴素贝叶斯保存指标")).toHaveTextContent("0.8");
 fireEvent.click(screen.getByRole("button",{name:"比较所有模型"}));
 const table=screen.getByRole("table");expect(within(table).getAllByRole("row")).toHaveLength(3);
 const secondRow=within(table).getByRole("rowheader",{name:"高斯朴素贝叶斯"}).closest("tr")!;
 expect(within(secondRow).getAllByRole("cell")[1]).toHaveTextContent("未记录");
 fireEvent.click(screen.getByRole("button",{name:"收起模型比较"}));expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("历史单模型不能复制给多个模型，未知评估方式和缺失数值不补默认",()=>{
 render(<MlResultSummary metadata={{model_keys:["random_forest","gaussian_nb"],model_key:"random_forest",nested_cv_mean_accuracy:0.3,roc_auc:0.9,samples:null,raw_feature_number:NaN}} availableFiles={[]} onOpenFile={vi.fn()}/>);
 expect(screen.getByText("1 个模型")).toBeInTheDocument();expect(screen.getAllByRole("option")).toHaveLength(1);
 expect(screen.getByText("未记录评估方式",{exact:true})).toBeInTheDocument();expect(screen.queryByText("折外 ROC AUC",{exact:true})).not.toBeInTheDocument();
 expect(screen.getByText("ROC AUC",{exact:true})).toBeInTheDocument();
 expect(screen.getAllByText("未记录",{exact:true}).length).toBeGreaterThan(1);expect(screen.queryByRole("button",{name:"比较所有模型"})).not.toBeInTheDocument();
});

it("未启用稳定筛选不被描述成已计算稳定集合，名称作为文本显示",()=>{
 render(<MlResultSummary metadata={{...metadata,label_col:"<script>bad()</script>",stability_selection:{enabled:false},models:[{...first,nested_cv_mean_accuracy:Infinity}]}} availableFiles={[]} onOpenFile={vi.fn()}/>);
 expect(screen.getByText("本次未启用稳定特征筛选")).toBeInTheDocument();expect(screen.queryByText(/最终稳定集合/)).not.toBeInTheDocument();
 expect(screen.getByLabelText("随机森林保存指标").querySelector("dd")?.textContent).toBe("未记录");expect(screen.getByText("<script>bad()</script>")).toBeInTheDocument();expect(document.querySelector("script")).toBeNull();
});

it("没有实际模型记录时不从用户选择或输出文件名推测指标",()=>{
 const view=render(<MlResultSummary metadata={{model_keys:["random_forest"],stability_selection:{enabled:true}}} availableFiles={["model_comparison.csv"]} onOpenFile={vi.fn()}/>);
 expect(screen.queryByRole("region",{name:"机器学习结果概览"})).not.toBeInTheDocument();
 view.rerender(<MlResultSummary metadata={null} availableFiles={[]} onOpenFile={vi.fn()}/>);expect(screen.queryByText("模型评估与稳定特征")).not.toBeInTheDocument();
});

function result(status:JobResultsResponse["job"]["status"]="completed"):JobResultsResponse{
 return {success:true,status,job:{id:"ml-summary",job_id:"ml-summary",module:"ml-analysis",status,job_type:"script_hub",progress:100},result:{metadata},assets:[],outputs:[
  {kind:"png",label:"ROC 图",url:"/api/script-hub/results/ml-summary/models/random_forest/ROC_AUC.png"},
  {kind:"csv",label:"feature_stability.csv",url:"/api/script-hub/results/ml-summary/%E6%95%B0%E6%8D%AE%20%E9%9B%86/feature_stability.csv"},
  {kind:"csv",label:"model_comparison.csv",url:"/api/script-hub/results/ml-summary/data/model_comparison.csv"}]};
}
it("概览按钮打开真实结果表并保存选择，不提前读取全部模型文件",async()=>{
 const fetcher=vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify({success:true,columns:["feature","selection_frequency"],rows:[["IGHG1","1.00000000001e-9"]],total_rows:1,matched_rows:1,offset:0,limit:25}),{headers:{"Content-Type":"application/json"}})));
 vi.stubGlobal("fetch",fetcher);
 const data=result(),original=JSON.stringify(data),view=render(<JobResultPanel result={data} loading={false}/>,{wrapper:MemoryRouter});
 expect(fetcher).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"查看特征稳定性表"}));
 expect(await screen.findByText("1.00000000001e-9",{exact:true})).toBeInTheDocument();expect(screen.getByLabelText("结果文件")).toHaveTextContent("feature_stability.csv");
 const read=fetcher.mock.calls.find(call=>call[1]?.method==="POST");expect(JSON.parse(read![1].body).url).toBe(data.outputs[1].url);
 expect(JSON.stringify(data)).toBe(original);
 view.unmount();render(<JobResultPanel result={data} loading={false}/>,{wrapper:MemoryRouter});
 await waitFor(()=>expect(screen.getByLabelText("结果文件")).toHaveTextContent("feature_stability.csv"));
});

it("未完成或失败任务不把残留元数据标成最终模型结果",()=>{
 const view=render(<JobResultPanel result={result("failed")} loading={false}/>,{wrapper:MemoryRouter});
 expect(screen.queryByText("模型评估与稳定特征")).not.toBeInTheDocument();
 view.rerender(<JobResultPanel result={result("running")} loading={false}/>);expect(screen.queryByText("模型评估与稳定特征")).not.toBeInTheDocument();
});

it("同任务刷新保留模型和比较视图，另一任务不沿用旧选择",()=>{
 const view=render(<MlResultSummary storageKey="ml-one" metadata={metadata} availableFiles={[]} onOpenFile={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText("查看模型评估"),{target:{value:"gaussian_nb:0"}});fireEvent.click(screen.getByRole("button",{name:"比较所有模型"}));view.unmount();
 const restored=render(<MlResultSummary storageKey="ml-one" metadata={metadata} availableFiles={[]} onOpenFile={vi.fn()}/>);
 expect(screen.getByLabelText("查看模型评估")).toHaveValue("gaussian_nb:0");expect(screen.getByRole("table")).toBeInTheDocument();restored.unmount();
 render(<MlResultSummary storageKey="ml-two" metadata={metadata} availableFiles={[]} onOpenFile={vi.fn()}/>);
 expect(screen.getByLabelText("查看模型评估")).toHaveValue("random_forest:0");expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
