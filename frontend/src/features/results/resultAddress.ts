export type ResultSelection = {module: string; output: string; section: string};
export type ResultBrowseFilters = {query: string; content: string; chain: string; comparison: string; page: number; thumbnails: boolean};
export type ResultAddress = {jobId: string; selection: ResultSelection; filters: ResultBrowseFilters};
export type ResultAddressBinding = {value: ResultAddress | null; update: (value: ResultAddress) => void};

export const defaultResultFilters: ResultBrowseFilters = {query:"", content:"", chain:"", comparison:"", page:0, thumbnails:false};
const addressKeys = ["result_job","result_module","result_output","result_section","result_query","result_content","result_chain","result_comparison","result_page","result_thumbnails"];

export function readResultAddress(params: URLSearchParams): ResultAddress | null {
  const jobId=params.get("result_job");
  if (!jobId) return null;
  const page=Number(params.get("result_page"));
  return {
    jobId, selection:{module:params.get("result_module") || "", output:params.get("result_output") || "", section:params.get("result_section") || ""},
    filters:{query:params.get("result_query") || "", content:params.get("result_content") || "", chain:params.get("result_chain") || "", comparison:params.get("result_comparison") || "", page:Number.isFinite(page)?Math.max(0,Math.floor(page)):0, thumbnails:params.get("result_thumbnails")==="1"},
  };
}

export function clearResultAddress(params: URLSearchParams): URLSearchParams {
  const next=new URLSearchParams(params);
  addressKeys.forEach(key=>next.delete(key));
  return next;
}

export function writeResultAddress(params: URLSearchParams, value: ResultAddress): URLSearchParams {
  const next=clearResultAddress(params);
  const fields: Record<string,string> = {
    result_job:value.jobId, result_module:value.selection.module, result_output:value.selection.output, result_section:value.selection.section,
    result_query:value.filters.query, result_content:value.filters.content, result_chain:value.filters.chain, result_comparison:value.filters.comparison,
    result_page:value.filters.page?String(value.filters.page):"", result_thumbnails:value.filters.thumbnails?"1":"",
  };
  Object.entries(fields).forEach(([key,text])=>{if(text)next.set(key,text)});
  return next;
}
