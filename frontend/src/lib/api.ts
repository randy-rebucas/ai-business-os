// Thin client for the FastAPI backend. All calls go through Next's /api rewrite (same origin),
// so the httpOnly session cookie is sent automatically.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }

  /** Field errors from a 422 response, keyed by the last path segment. */
  fieldErrors(): Record<string, string> {
    if (!Array.isArray(this.details)) return {};
    const out: Record<string, string> = {};
    for (const d of this.details as { loc?: string[]; msg?: string }[]) {
      if (!Array.isArray(d?.loc) || typeof d.msg !== "string") continue; // other detail shapes (e.g. config issues)
      const key = d.loc[d.loc.length - 1];
      if (key && !out[key]) out[key] = d.msg.replace(/^Value error, /, "");
    }
    return out;
  }
}

let activeOrgId: string | null = null;

export function setActiveOrgId(id: string | null) {
  activeOrgId = id;
}

export function getActiveOrgId() {
  return activeOrgId;
}

type Options = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Tenant-scoped endpoint: `true` sends the active org; a string sends that org id. */
  org?: boolean | string;
  signal?: AbortSignal;
};

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "abos" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const orgId = typeof opts.org === "string" ? opts.org : opts.org ? activeOrgId : null;
  if (orgId) headers["X-Org-Id"] = orgId;

  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
      signal: opts.signal,
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection and try again.");
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Request failed (${res.status})`,
      err?.details);
  }
  return data as T;
}

/** SWR fetcher. Keys are [path, orgId|null] so tenant data never leaks across workspace switches. */
export const swrFetcher = ([path, orgId]: [string, string | null]) => api(path, { org: orgId ?? false });
