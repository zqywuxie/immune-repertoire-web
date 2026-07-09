import { apiClient } from "./client";

export interface DirectoryItem {
  name: string;
  path: string;
  has_children: boolean;
  type?: string; // "directory"
  size?: number;
}

export interface DirectoryListResponse {
  current_path: string;
  directories: DirectoryItem[];
  parent_path: string | null;
  roots: string[];
}

export interface BrowseResponse {
  items: DirectoryItem[];
  current_path: string;
  parent_path: string | null;
  roots: string[];
}

/** List directories only (for path picker). */
export function listDirectories(parentPath?: string): Promise<DirectoryListResponse> {
  return apiClient.get<DirectoryListResponse>("/api/directories", {
    parent_path: parentPath || undefined,
  } as Record<string, string | undefined>);
}

/** Full browse with optional file filter. */
export function browseDirectory(path?: string, filter?: string): Promise<BrowseResponse> {
  return apiClient.get<BrowseResponse>("/api/browse-directory", {
    path: path || undefined,
    filter: filter || undefined,
  } as Record<string, string | undefined>);
}
