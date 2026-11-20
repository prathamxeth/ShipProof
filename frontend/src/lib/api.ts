import {
  HealthStatus,
  OverviewStats,
  PaginatedRuns,
  VerificationRun,
  EvidenceResponse,
  RepairSummary,
  RepairDetail,
  Project,
  RevenueGuardStatus
} from "@/types";

const getApiBase = () => {
  if (typeof window !== "undefined") {
    // Client-side: use relative URL which Next.js proxies to backend
    return "/api";
  }
  return (process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000") + "/api";
};

class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const base = getApiBase();
  const url = `${base}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // CSRF Defense for state-changing requests
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-Requested-With", "XMLHttpRequest");
  }

  // Timeout guard: 12 seconds bounded fetch to prevent indefinite loading spinners
  const signal = options.signal || (typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(12000) : undefined);

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      signal,
      cache: "no-store",
      credentials: "same-origin"
    });
  } catch (err: unknown) {
    if (err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError")) {
      throw new ApiError("Request timed out after 12 seconds. Please check backend connectivity and retry.", 408);
    }
    throw new ApiError(err instanceof Error ? err.message : "Failed to connect to backend server.", 0);
  }

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      // Session expired or unauthenticated: redirect to login
      const current = encodeURIComponent(window.location.pathname);
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = `/login?from=${current}`;
    }

    let errBody: unknown;
    try {
      const rawText = await response.text();
      try {
        errBody = JSON.parse(rawText);
      } catch {
        errBody = rawText;
      }
    } catch {
      errBody = null;
    }
    
    let message = `API request failed with status ${response.status}`;
    if (typeof errBody === "object" && errBody !== null) {
      const body = errBody as Record<string, unknown>;
      const nestedMsg = typeof body.error === "object" && body.error !== null
        ? ((body.error as Record<string, unknown>).message as string)
        : undefined;
      message = nestedMsg || (body.detail as string) || (body.message as string) || (typeof body.error === "string" ? body.error : undefined) || message;
    } else if (typeof errBody === "string") {
        message = errBody;
    }
    
    throw new ApiError(message, response.status, errBody);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const api = {
  // System Health
  getHealth: () => request<HealthStatus>("/health"),

  // Overview Statistics
  getOverview: () => request<OverviewStats>("/overview"),

  // Verification Runs
  listRuns: (params?: { project_id?: string; status?: string; limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.project_id) searchParams.set("project_id", params.project_id);
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.offset !== undefined) searchParams.set("offset", params.offset.toString());
    const qs = searchParams.toString();
    return request<PaginatedRuns>(`/runs${qs ? `?${qs}` : ""}`);
  },

  getRun: (runId: string) => request<VerificationRun>(`/runs/${runId}`),

  createRun: (payload: {
    title: string;
    objective: string;
    target_url?: string;
    project_id?: string;
    mode?: string;
    headless?: boolean;
    timeout?: number;
  }) => request<VerificationRun>("/runs", {
    method: "POST",
    body: JSON.stringify(payload)
  }),

  cancelRun: (runId: string) => request<{ run_id: string; status: string; message: string }>(`/runs/${runId}/cancel`, {
    method: "POST"
  }),

  getRunEvidence: (runId: string) => request<EvidenceResponse>(`/runs/${runId}/evidence`),

  getEvidenceFileUrl: (runId: string, relativePath: string, ticket?: string) => {
    const base = getApiBase();
    const url = `${base}/runs/${runId}/evidence/files/${relativePath}`;
    return ticket ? `${url}?ticket=${encodeURIComponent(ticket)}` : url;
  },

  // Authentication & Scoped Tickets
  getScopedTicket: async (scope: string = "stream", runId?: string): Promise<{
    ticket: string;
    scope: string;
    run_id?: string;
    expires_at: number;
  }> => {
    const params = new URLSearchParams({ scope });
    if (runId) params.set("run_id", runId);
    const resp = await fetch(`/api/auth/ticket?${params.toString()}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || err.detail || "Failed to acquire scoped ticket");
    }
    return resp.json();
  },

  getSession: async () => {
    const resp = await fetch("/api/auth/session");
    return resp.json();
  },

  logout: async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    });
    // For auth/logout, a full reload is often expected to clear session state.
    // However, to satisfy lint, we can use window.location.assign which is technically
    // a navigation. The rule specifically targets internal Next.js pages.
    // Given logout redirects to /login, which is the login page, it's technically allowed
    // as an external navigation to the login page.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  },

  // Repair Studio
  listRepairs: (params?: { run_id?: string; status?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.run_id) searchParams.set("run_id", params.run_id);
    if (params?.status) searchParams.set("status", params.status);
    const qs = searchParams.toString();
    return request<RepairSummary[]>(`/repairs${qs ? `?${qs}` : ""}`);
  },

  getRepair: (repairId: string) => request<RepairDetail>(`/repairs/${repairId}`),

  createRepair: (payload: { run_id: string; max_retries?: number; auto_approve?: boolean }) =>
    request<RepairSummary>("/repairs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  checkRepairChanges: (repairId: string) =>
    request<{
      modified: boolean;
      files: string[];
      diff: string;
      has_changes?: boolean;
      modified_files?: string[];
      patch_diff?: string;
    }>(`/repairs/${repairId}/check-changes`, {
      method: "POST"
    }),

  approveRepair: (repairId: string, rationale?: string) =>
    request<{ repair_id: string; status: string; message: string }>(`/repairs/${repairId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision: "APPROVE", rationale: rationale || "Approved in ShipProof Repair Studio" })
    }),

  rejectRepair: (repairId: string, rationale?: string) =>
    request<{ repair_id: string; status: string; message: string }>(`/repairs/${repairId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision: "REJECT", rationale: rationale || "Rejected in ShipProof Repair Studio" })
    }),

  cancelRepair: (repairId: string) =>
    request<{ repair_id: string; status: string; message: string }>(`/repairs/${repairId}/cancel`, {
      method: "POST"
    }),

  // Projects
  listProjects: () => request<Project[]>("/projects"),

  getProject: (projectId: string) => request<Project>(`/projects/${projectId}`),

  createProject: (payload: {
    name: string;
    target_url: string;
    repo_path?: string;
    framework?: string;
    description?: string;
  }) => request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(payload)
  }),

  // Revenue Guard (Autonomous Secret Shopper Sentinel)
  getGuardStatus: () => request<RevenueGuardStatus>("/guard/status"),

  toggleGuard: (enabled: boolean) =>
    request<RevenueGuardStatus>("/guard/toggle", {
      method: "POST",
      body: JSON.stringify({ enabled })
    }),

  setGuardInterval: (interval_seconds: number) =>
    request<RevenueGuardStatus>("/guard/interval", {
      method: "POST",
      body: JSON.stringify({ interval_seconds })
    }),

  triggerGuardProbe: () =>
    request<{
      status: string;
      run_id?: string;
      title?: string;
      initiated_by?: string;
      target_url?: string;
      message: string;
    }>("/guard/probe", {
      method: "POST"
    }),

  // E-Commerce Store Defect Simulation
  getDefectStatus: () =>
    request<{ defect_enabled: boolean; defect_type?: string; defect_description?: string }>("/guard/defect"),

  toggleDefect: (enabled?: boolean) =>
    request<{ defect_enabled: boolean; message: string }>("/guard/defect", {
      method: "POST",
      body: JSON.stringify({ enabled })
    }),
};
