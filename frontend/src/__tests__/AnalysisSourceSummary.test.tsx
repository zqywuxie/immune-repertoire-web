import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SourceSummary } from "../features/scripthub/modules/shared";
import type { ScriptHubSourceContext } from "../features/jobs/forms";

const context: ScriptHubSourceContext = {assetSetId:"Set1",profilePath:"/private/uploads/profile.csv",
  pepPaths:["/private/uploads/001__TRB.csv"],transcriptomePath:"/private/uploads/expression.csv",
  deconvolutionPath:"/private/uploads/cells.csv",sampleNames:[],chains:[],profileFields:[],groupFields:[],pepColumns:[]};
afterEach(cleanup);
describe("consumed analysis source summary",()=>{
  it("shows only consumed originals and readable filenames",()=>{
    render(<SourceSummary sourceContext={{...context,inspectedInputTypes:["profile"]}}/>);
    expect(screen.getByText("profile.csv")).toBeTruthy();
    expect(screen.queryByText("expression.csv")).toBeNull();
    expect(screen.queryByText("转录组")).toBeNull();
    expect(screen.queryByText(/private/)).toBeNull();
  });
  it("describes upstream-only input without reporting missing originals",()=>{
    render(<SourceSummary sourceContext={{...context,inspectedInputTypes:[]}}/>);
    expect(screen.getByText("前置分析结果（在下方选择）")).toBeTruthy();
    expect(screen.queryByText("尚未选择")).toBeNull();
    expect(screen.queryByText("profile.csv")).toBeNull();
  });
  it("keeps the existing unscoped multi-module summary",()=>{
    render(<SourceSummary sourceContext={context}/>);
    expect(screen.getByText("profile.csv")).toBeTruthy();
    expect(screen.getByText("expression.csv")).toBeTruthy();
    expect(screen.getByText("cells.csv")).toBeTruthy();
  });
});
