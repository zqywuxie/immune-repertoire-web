import { describe, expect, it } from "vitest";
import { unifiedPayload } from "../shared/api/unified";
const file = { id: "uploaded-id", name: "profile.csv", columns: ["sample_id", "metric", "other"], row_count: 2 };
const scheme = { id: "real-scheme", name: "真实方案", description: "", required_fields: [{ field: "Sample" }] };
describe("unified analysis contract", () => {
  it("uses the execution module separately from the actual scheme", () => {
    expect(unifiedPayload(file, "scheme", scheme, { Sample: "sample_id" }, [], "", "")).toEqual({ module: "analysis.execute-unified", payload: { file_id: "uploaded-id", mode: "scheme", scheme_id: "real-scheme", field_mapping: { Sample: "sample_id" }, parameters: {} } });
  });
  it("passes only selected custom metrics with the sample column", () => {
    expect(unifiedPayload(file, "custom", null, {}, ["metric"], "sample_id", "S1").payload).toMatchObject({ selected_fields: ["metric"], parameters: { sample_column: "sample_id", baseline_sample: "S1" } });
  });
  it("rejects stale, duplicate or missing mappings before submitting", () => {
    expect(() => unifiedPayload(file,"scheme",scheme,{},[],"","")).toThrow("必需字段");
    expect(() => unifiedPayload(file,"scheme",scheme,{ Sample:"sample_id", other:"sample_id" },[],"","")).toThrow("多个标准字段");
    expect(() => unifiedPayload(file,"custom",null,{},["missing"],"sample_id","")).toThrow("当前文件");
  });
});
