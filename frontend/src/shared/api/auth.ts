import { apiClient } from "./client";

export interface AuthPrincipal {
  user_id?: number | null;
  username?: string;
  role?: string;
  auth_mode?: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  success: boolean;
  token?: string;
  user?: AuthPrincipal;
  message?: string;
}

/** Fetch the current authenticated principal. */
export function getAuthMe(): Promise<AuthPrincipal> {
  return apiClient.get<AuthPrincipal>("/api/auth/me");
}

/** Login with username/password. */
export function login(data: LoginRequest): Promise<LoginResponse> {
  return apiClient.post<LoginResponse>("/api/auth/login", data);
}

/** Logout current session. */
export function logout(): Promise<{ success: boolean }> {
  return apiClient.post<{ success: boolean }>("/api/auth/logout");
}
