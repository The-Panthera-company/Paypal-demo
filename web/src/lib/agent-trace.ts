// ---- Public agent trace (GET /agents/runs, /agents/runs/{id}, /agents/activity) ----
// Donor fields are removed by the API. Safe to call from the browser.
export type TraceStep = {
  seq: number;
  at: string | null;
  actor: string | null;
  step: string;
  tool: string | null;
  status: "ok" | "skipped" | "blocked" | "error" | string;
  title: string;
  input: unknown;
  result: unknown;
  rule: string | null;
  reason: string | null;
};
export type AgentRun = {
  id: number;
  run_at: string;
  report_text: string | null;
  trace: TraceStep[];
  chosen: { project_id: number | null; title: string | null; amount_cents: number }[];
  skipped: { project_id: number | null; title: string | null; reason: string | null }[];
};
export type AgentActivity = {
  id: number;
  at: string;
  actor: string;
  action: string;
  title: string;
  status: "ok" | "pending" | "blocked" | "error" | string;
  rule: string | null;
  project_id: number | null;
  project_title: string | null;
  run_id: number | null;
};

const PUBLIC = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const BASE = (typeof window === "undefined" ? process.env.API_INTERNAL_URL?.replace(/\/$/, "") : undefined) || PUBLIC;

export class AgentApiError extends Error {
  constructor(public status: number) {
    super(`Agent trace request failed (${status})`);
  }
}

async function agentGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (!BASE) throw new AgentApiError(0);
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", signal });
  if (!res.ok) throw new AgentApiError(res.status);
  return (await res.json()) as T;
}
export const fetchAgentRuns = (limit = 10, signal?: AbortSignal) => agentGet<AgentRun[]>(`/agents/runs?limit=${limit}`, signal);
export const fetchAgentRun = (id: number | string, signal?: AbortSignal) => agentGet<AgentRun>(`/agents/runs/${id}`, signal);
export const fetchAgentActivity = (limit = 50, signal?: AbortSignal) => agentGet<AgentActivity[]>(`/agents/activity?limit=${limit}`, signal);
