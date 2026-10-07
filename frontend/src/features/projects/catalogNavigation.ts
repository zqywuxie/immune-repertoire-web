export function projectCatalogNavigationState(location: { pathname: string; search: string }) {
  return location.pathname === "/management/projects" ? { projectCatalogReturn: location.pathname + location.search } : undefined;
}

export function projectCatalogReturnPath(state: unknown) {
  const path = state && typeof state === "object" && "projectCatalogReturn" in state ? state.projectCatalogReturn : null;
  return typeof path === "string" && /^\/management\/projects(?:\?[^#]*)?$/.test(path) ? path : "/management/projects";
}
