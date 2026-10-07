import { describe, expect, it, vi } from "vitest";
import { inputDataForAsset, inputAssetReturnPath, validateInputAsset } from "../features/analysis/InputAssetIntent";
vi.mock("../shared/api/projects",()=>({getProjectAsset:vi.fn()}));
const asset={id:"old",project_id:"p1",asset_type:"profile",original_name:"同名.csv",storage_path:"/inputs/old.csv",size:1,metadata:{asset_set:"甲",superseded:true}} as any;
const base={projectId:"p1",assetSetName:"甲",pepPaths:["/inputs/pep"],profilePath:"/inputs/current.csv",transcriptomePath:"/inputs/expression.tsv",deconvolutionPath:""};
describe("明确输入文件身份",()=>{
 it("同范围替换目标类型，跨范围清空其他旧输入",()=>{
  expect(inputDataForAsset(base,asset)).toEqual({...base,profilePath:"/inputs/old.csv"});
  expect(inputDataForAsset({...base,assetSetName:"乙"},asset)).toEqual({projectId:"p1",assetSetName:"甲",pepPaths:[],profilePath:"/inputs/old.csv",transcriptomePath:"",deconvolutionPath:""});
  expect(inputDataForAsset(base,{...asset,asset_type:"pep"}).pepPaths).toEqual(["/inputs/old.csv"]);
 });
 it("拒绝跨项目、跨集及非输入，空范围允许定位明确文件",()=>{
  expect(()=>validateInputAsset(asset,"p2","甲")).toThrow("当前项目");
  expect(()=>validateInputAsset(asset,"p1","乙")).toThrow("当前数据集");
  expect(()=>validateInputAsset({...asset,asset_type:"processed_result"},"p1","甲")).toThrow("不是分析输入");
  expect(validateInputAsset(asset,"p1","")).toBe(asset);
 });
 it("来源返回保留筛选页码且不能跳到外部或其他项目",()=>{
  const path="/management/projects/p1?tab=assets&asset_set=甲&history=true&file_page=3&asset=old#file";
  expect(decodeURI(inputAssetReturnPath("p1",asset,path))).toBe(path);
  const fallback=inputAssetReturnPath("p1",asset,"");
  expect(inputAssetReturnPath("p1",asset,"https://other.example/management/projects/p1")).toBe(fallback);
  expect(inputAssetReturnPath("p1",asset,"/management/projects/p2")).toBe(fallback);
 });
});
