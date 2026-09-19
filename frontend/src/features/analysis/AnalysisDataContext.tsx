import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
export type AnalysisData = { projectId:string; assetSetName:string; pepPaths:string[]; profilePath:string; transcriptomePath:string; deconvolutionPath?:string };
const Context = createContext<{data:AnalysisData | null; setData:(data:AnalysisData)=>void}>({data:null,setData:()=>{}});
export function AnalysisDataProvider({children}:{children:ReactNode}) {
  const [data,setData]=useState<AnalysisData|null>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem("analysis-selection") || "null");
      return saved && typeof saved.projectId === "string" && typeof saved.assetSetName === "string"
        ? { projectId:saved.projectId, assetSetName:saved.assetSetName, pepPaths:[], profilePath:"", transcriptomePath:"", deconvolutionPath:"" } : null;
    } catch { return null; }
  });
  useEffect(() => {
    try {
      if (data) sessionStorage.setItem("analysis-selection", JSON.stringify({projectId:data.projectId, assetSetName:data.assetSetName}));
    } catch { /* Storage can be disabled; in-memory navigation still works. */ }
  }, [data]);
  return <Context.Provider value={{data,setData}}>{children}</Context.Provider>;
}
export const useAnalysisData = () => useContext(Context);
