export function acceptsPepResult(module: string, payload: Record<string, unknown>): boolean {
  return (module === "volcano" && ["usage", "vj_usage"].includes(String(payload.input_mode)))
    || module === "umapin"
    || (module === "ml-analysis" && ["vj", "profile_vj"].includes(String(payload.mode)))
    || (module === "mait-nkt" && payload.tra_source === "pep_analysis");
}

export function orderPepDependencies(modules: string[], usesResult: (module: string) => boolean): string[] {
  const ordered = [...modules];
  const source = ordered.indexOf("pep-analysis");
  const firstDependent = ordered.findIndex(module => module !== "pep-analysis" && usesResult(module));
  if (source >= 0 && firstDependent >= 0 && source > firstDependent) {
    ordered.splice(source, 1);
    ordered.splice(firstDependent, 0, "pep-analysis");
  }
  return ordered;
}

export function batchResultSource(module: string, modules: string[], payloadFor: (module: string) => Record<string, unknown>): string | undefined {
  if (modules.includes("pep-analysis") && acceptsPepResult(module, payloadFor(module))) return "pep-analysis";
  if (module === "go-kegg-enrichment" && modules.includes("volcano") && payloadFor("volcano").input_mode === "expression") return "volcano";
  return undefined;
}

export function orderBatchDependencies(modules: string[], sourceFor: (module: string) => string | undefined): string[] {
  const ordered: string[] = [];
  const visit = (module: string) => {
    if (ordered.includes(module)) return;
    const source = sourceFor(module);
    if (source && modules.includes(source)) visit(source);
    ordered.push(module);
  };
  modules.forEach(visit);
  return ordered;
}
