import { apiClient } from "./client";

export interface AuthPrincipal {
  user_id?: number | null;
  username?: string;
  email?: string;
  role?: string;
  auth_mode?: string;
}
export interface LoginRequest { username: string; password: string }
export interface RegisterRequest extends LoginRequest { email: string; confirm_password: string }
export interface LoginResponse { success: boolean; user?: AuthPrincipal; message?: string }
export interface AuthOptions { csrf_token: string; registration_enabled: boolean }

export function getAuthMe(): Promise<AuthPrincipal> {
  return apiClient.get("/api/auth/me", undefined, { skipCache: true, maxRetries: 0 });
}
export function getAuthOptions(): Promise<AuthOptions> {
  return apiClient.get("/api/auth/options", undefined, { skipCache: true, maxRetries: 0 });
}
async function mutateSession<T>(path: string, data?: unknown): Promise<T> {
  const { csrf_token } = await getAuthOptions();
  const response = await apiClient.post<T>(path, data, { "X-CSRF-Token": csrf_token });
  apiClient.invalidateCache();
  return response;
}
export function login(data: LoginRequest): Promise<LoginResponse> {
  return mutateSession("/api/auth/login", data);
}
export function register(data: RegisterRequest): Promise<LoginResponse> {
  return mutateSession("/api/auth/register", data);
}
export function logout(): Promise<{ success: boolean }> {
  return mutateSession("/api/auth/logout");
}
