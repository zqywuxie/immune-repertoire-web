export interface ApiClientOptions {
  baseUrl?: string;
}

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

// ── In-memory request cache ─────────────────────────────────────────

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  staleAt: number;
}

const cache = new Map<string, CacheEntry<unknown>>();
const pendingRequests = new Map<string, Promise<unknown>>();

const CACHE_TTL = 30_000;       // 30 seconds fresh
const CACHE_STALE = 120_000;    // 2 minutes stale-while-revalidate

function cacheKey(path: string, init?: RequestInit): string {
  return `${init?.method || "GET"}:${path}`;
}

function getCached<T>(key: string): { data: T; stale: boolean } | null {
  const entry = cache.get(key) as CacheEntry<T> | undefined;
  if (!entry) return null;
  const age = Date.now() - entry.timestamp;
  if (age > CACHE_STALE) {
    cache.delete(key);
    return null;
  }
  return { data: entry.data, stale: age > CACHE_TTL };
}

function setCache<T>(key: string, data: T): void {
  cache.set(key, { data, timestamp: Date.now(), staleAt: Date.now() + CACHE_STALE });
}

// ── API Client ───────────────────────────────────────────────────────

export class ApiClient {
  private readonly baseUrl: string;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? defaultBaseUrl).replace(/\/$/, "");
  }

  async get<T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined>,
    options?: { skipCache?: boolean; maxRetries?: number }
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`, window.location.origin);
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });

    const fullPath = url.pathname + url.search;
    const key = cacheKey(fullPath);
    const skipCache = options?.skipCache || false;
    const maxRetries = options?.maxRetries ?? 2;

    // Return fresh cache hit immediately
    if (!skipCache) {
      const cached = getCached<T>(key);
      if (cached && !cached.stale) {
        return cached.data;
      }
      // Stale — return immediately but revalidate in background
      if (cached && cached.stale) {
        this.fetchAndCache<T>(fullPath, key, maxRetries).catch(() => {});
        return cached.data;
      }
    }

    // Deduplicate in-flight requests
    const pending = pendingRequests.get(key);
    if (pending) {
      return pending as Promise<T>;
    }

    const promise = this.fetchAndCache<T>(fullPath, key, maxRetries);
    pendingRequests.set(key, promise);
    const result = await promise;
    pendingRequests.delete(key);
    return result;
  }

  private async fetchAndCache<T>(fullPath: string, cacheKey: string, maxRetries: number): Promise<T> {
    let lastError: unknown;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const data = await this.request<T>(fullPath);
        setCache(cacheKey, data);
        return data;
      } catch (err) {
        lastError = err;
        if (err instanceof ApiError && err.status >= 500 && attempt < maxRetries) {
          // Exponential backoff for server errors
          await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 300));
          continue;
        }
        throw err;
      }
    }
    throw lastError;
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      credentials: "include",
      ...init
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      const message =
        typeof payload === "object" && payload && "message" in payload
          ? String((payload as { message?: unknown }).message)
          : response.statusText;
      throw new ApiError(message, response.status, payload);
    }
    return payload as T;
  }

  /** Invalidate all cached GET responses, e.g. after a mutation. */
  invalidateCache(): void {
    cache.clear();
    pendingRequests.clear();
  }

  /** Invalidate cached responses matching a path prefix. */
  invalidatePath(prefix: string): void {
    for (const key of cache.keys()) {
      if (key.includes(prefix)) cache.delete(key);
    }
    for (const key of pendingRequests.keys()) {
      if (key.includes(prefix)) pendingRequests.delete(key);
    }
  }
}

export const apiClient = new ApiClient();
