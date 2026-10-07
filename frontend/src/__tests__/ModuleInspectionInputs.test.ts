import { describe, expect, it } from "vitest";
import { getModuleInspectionInputs, getCombinedInspectionScope } from "../features/scripthub/moduleRequirements";

describe("analysis input consumption", () => {
  it.each([
    ["profile", {}, ["profile"]],
    ["pep-analysis", {}, ["pep", "profile"]],
    ["volcano", {input_mode:"expression"}, ["transcriptome"]],
    ["volcano", {input_mode:"usage"}, []],
    ["go-kegg-enrichment", {input_mode:"expression"}, ["transcriptome"]],
    ["go-kegg-enrichment", {input_mode:"deg"}, []],
    ["umapin", {}, []],
    ["umap", {}, ["profile"]],
    ["ml-analysis", {mode:"vj"}, ["profile"]],
    ["mait-nkt", {tra_source:"pep_analysis"}, ["profile"]],
    ["immune-infiltration", {}, ["profile", "deconvolution"]],
    ["immune-infiltration-sample-pathway", {}, ["profile", "deconvolution", "transcriptome"]],
  ] as const)("%s checks consumed originals", (module, config, expected) => {
    expect(getModuleInspectionInputs(module, config)).toEqual(expected);
  });
});


describe("combined inspection scope",()=>{
  it("checks independent inputs without cross-analysis sample matching",()=>{
    expect(getCombinedInspectionScope(["profile","volcano"],{volcano:{input_mode:"expression"}}))
      .toEqual({inputTypes:["profile","transcriptome"],alignmentGroups:[]});
  });
  it("changes alignment requirements even when the original input union is unchanged",()=>{
    const separate=getCombinedInspectionScope(["profile","charts"],{});
    const joint=getCombinedInspectionScope(["profile","charts","topclone"],{});
    expect(separate.inputTypes).toEqual(joint.inputTypes);
    expect(separate.alignmentGroups).toEqual([]);
    expect(joint.alignmentGroups).toEqual([["pep","profile"]]);
  });
  it("deduplicates joint requirements and defaults usage mode without an expression matrix",()=>{
    expect(getCombinedInspectionScope(["topclone","pep-analysis","volcano"],{}, {pepPaths:["pep"]}))
      .toEqual({inputTypes:["pep","profile"],alignmentGroups:[["pep","profile"]]});
  });
});
