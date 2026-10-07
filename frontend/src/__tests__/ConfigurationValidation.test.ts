import { expect, it } from "vitest";
import { configurationIssue, validateAnalysisPayload } from "../features/scripthub/configurationValidation";
const grouped={grouptype_fields:["group"],selected_group_values:{group:["A"]},selected_samples_by_group:{group:{A:["S1"]}}};
it("指标、分组值和实际分组样本依次核验",()=>{
  expect(configurationIssue("profile",{})).toContain("指标范围");
  const metrics={param_begin:"metric",param_over:"metric"};
  expect(configurationIssue("profile",metrics)).toContain("分组字段");
  expect(configurationIssue("profile",{...metrics,grouptype_fields:["group"]})).toContain("分组值");
  expect(configurationIssue("profile",{...metrics,...grouped,selected_samples_by_group:{group:{A:[]}}})).toContain("group = A");
  expect(configurationIssue("profile",{...metrics,...grouped})).toBe("");
});
it("表达差异尊重显式清空的比较与样本",()=>{
  expect(configurationIssue("volcano",{input_mode:"expression",comparisons:[]})).toContain("组间比较");
  expect(configurationIssue("volcano",{input_mode:"expression",selected_expression_samples:[]})).toContain("至少选择一个样本");
  expect(configurationIssue("volcano",{input_mode:"expression",comparisons:["01_vs_02"],selected_expression_samples:["S1","S2"]})).toBe("");
});
it("本批次前置来源允许后续选择，但不能替代必填分类和执行来源确认",()=>{
  expect(configurationIssue("umapin",{},true)).toContain("分组字段");
  expect(configurationIssue("umapin",{category_col:"Category"},true)).toBe("");
  expect(()=>validateAnalysisPayload("umapin",{category_col:"Category"})).toThrow("缓存");
  expect(()=>validateAnalysisPayload("umapin",{category_col:"Category"},true)).not.toThrow();
});
it("复用差异结果不要求重新配置表达样本；图表仍需指定链与样本",()=>{
  expect(configurationIssue("go-kegg-enrichment",{input_mode:"deg",upstream_artifact_id:"deg-1",selected_expression_samples:[]})).toBe("");
  expect(configurationIssue("go-kegg-enrichment",{input_mode:"deg"})).toContain("来源差异表达结果");
  expect(configurationIssue("charts",{})).toContain("绘图的样本");
  expect(configurationIssue("charts",{samples:["S1"]})).toContain("链类型");
  expect(configurationIssue("charts",{samples:["S1"],selected_chains:["TRB"]})).toBe("");
});


const mlReady = { label_col: "group", ml_inspect_ok: true, selected_group_values: { group: ["01", "02"] },
  selected_samples_by_group: { group: { "01": ["001", "002"], "02": ["003", "004"] } } };
it.each(["profile", "profile_vj"])("机器学习 %s 在独立与批次配置中都需要指标范围", mode => {
  const input = { ...mlReady, mode, upstream_artifact_id: "actual-source" };
  for (const batch of [false, true]) {
    for (const range of [{}, { param_begin: "metric" }, { param_over: "metric" }, { param_begin: " ", param_over: "metric" }]) {
      expect(configurationIssue("ml-analysis", { ...input, ...range }, batch)).toContain("指标的起始列和结束列");
    }
    expect(configurationIssue("ml-analysis", { ...input, param_begin: "metric", param_over: "metric" }, batch)).toBe("");
  }
});
it("V/J 模式不强制指标表范围，但必须有实际来源或本批次前置结果", () => {
  const input = { ...mlReady, mode: "vj" };
  expect(configurationIssue("ml-analysis", input)).toContain("V/J 基因使用特征来源");
  expect(configurationIssue("ml-analysis", { ...input, upstream_artifact_id: "actual-source" })).toBe("");
  expect(configurationIssue("ml-analysis", { ...input, usage_path: "/legacy/usage" })).toBe("");
  expect(configurationIssue("ml-analysis", input, true)).toBe("");
  expect(configurationIssue("ml-analysis", { ...input, ml_inspect_ok: false }, true)).toBe("");
});
it("保留旧模式别名的实际范围与来源要求", () => {
  expect(configurationIssue("ml-analysis", { ...mlReady, mode: "profile+vj", upstream_artifact_id: "actual-source" })).toContain("指标的起始列和结束列");
  expect(configurationIssue("ml-analysis", { ...mlReady, mode: "usage" })).toContain("V/J 基因使用特征来源");
  expect(configurationIssue("ml-analysis", { ...mlReady, mode: "VJ", upstream_artifact_id: "actual-source" })).toBe("");
});
