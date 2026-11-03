// Admin console data. Server-only: ADMIN_TOKEN (the core API's admin bearer token) must never reach
// the browser, so these run in server components and server actions, never in client code.
import "server-only";

const API_URL = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL)?.replace(/\/$/, "");
const ADMIN_TOKEN = process.env.ADMIN_TOKEN ?? "";

export type AdminProject = {
  id: string;
  title: string;
  category: string;
  region: string;
  status: string;
  goal: number;
  raised: number;
  currency: string;
  frozen: boolean;
};
export type AdminCase = {
  id: string;
  projectId: string;
  projectTitle: string;
  rule: string;
  evidence: Record<string, unknown> | null;
  status: "open" | "cleared" | "confirmed";
  createdAt: string;
};
export type AdminMilestone = {
  id: string;
  seq: number;
  title: string;
  amount: number;
  match: number;
  currency: string;
  dueDate: string | null;
  status: string;
};
export type AuditEntry = {
  id: string;
  actor: string;
  action: string;
  inputs: Record<string, unknown> | null;
  ruleResult: string | null;
  reason: string | null;
  createdAt: string;
};

export type AdminData = {
  queue: AdminProject[];
  cases: AdminCase[];
  milestones: AdminMilestone[];
  audit: AuditEntry[];
  /** why the data is sample data, if it is */
  sampleReason: string | null;
};

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${ADMIN_TOKEN}`, ...init?.headers },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: { message?: string } };
    throw new Error(body.detail?.message ?? `${init?.method ?? "GET"} ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

type ApiProject = {
  id: number;
  title: string;
  category: string;
  region: string | null;
  status: string;
  goal_cents: number;
  raised_cents: number;
  currency: string;
  matching_frozen: boolean;
};

export async function getAdminData(): Promise<AdminData> {
  if (!API_URL) return { ...sample, sampleReason: "No NEXT_PUBLIC_API_URL: showing sample data." };
  if (!ADMIN_TOKEN) return { ...sample, sampleReason: "ADMIN_TOKEN is not set for the website: showing sample data." };

  const [queue, cases, milestones, audit, all] = await Promise.all([
    adminFetch<ApiProject[]>("/admin/projects?status=pending_review"),
    adminFetch<
      { id: number; project_id: number; rule: string; evidence: Record<string, unknown> | null; status: AdminCase["status"]; created_at: string }[]
    >("/admin/cases"),
    adminFetch<
      { id: number; seq: number; title: string; amount_cents: number; match_amount_cents: number; currency: string; due_date: string | null; status: string }[]
    >("/admin/milestones/held"),
    adminFetch<
      { id: number; actor: string; action: string; inputs: Record<string, unknown> | null; rule_result: string | null; reason: string | null; created_at: string }[]
    >("/admin/audit-log?limit=200"),
    adminFetch<ApiProject[]>("/projects?limit=200"),
  ]);
  const titles = new Map(all.map((p) => [p.id, p.title]));
  return {
    sampleReason: null,
    queue: queue.map((p) => ({
      id: String(p.id),
      title: p.title,
      category: p.category,
      region: p.region ?? "",
      status: p.status,
      goal: p.goal_cents,
      raised: p.raised_cents,
      currency: p.currency,
      frozen: p.matching_frozen,
    })),
    cases: cases.map((c) => ({
      id: String(c.id),
      projectId: String(c.project_id),
      projectTitle: titles.get(c.project_id) ?? `Project ${c.project_id}`,
      rule: c.rule,
      evidence: c.evidence,
      status: c.status,
      createdAt: c.created_at,
    })),
    milestones: milestones.map((m) => ({
      id: String(m.id),
      seq: m.seq,
      title: m.title,
      amount: m.amount_cents,
      match: m.match_amount_cents,
      currency: m.currency,
      dueDate: m.due_date,
      status: m.status,
    })),
    audit: audit.map((a) => ({
      id: String(a.id),
      actor: a.actor,
      action: a.action,
      inputs: a.inputs,
      ruleResult: a.rule_result,
      reason: a.reason,
      createdAt: a.created_at,
    })),
  };
}

/** Admin actions, called from server actions. Sample mode returns without calling anything. */
export async function verifyProject(id: string, approve: boolean, note?: string) {
  if (!API_URL || !ADMIN_TOKEN) return;
  await adminFetch(`/admin/projects/${id}/verify`, { method: "POST", body: JSON.stringify({ approve, note }) });
}
export async function resolveCase(id: string, action: "clear" | "confirm", note?: string) {
  if (!API_URL || !ADMIN_TOKEN) return;
  await adminFetch(`/admin/cases/${id}/resolve`, { method: "POST", body: JSON.stringify({ action, note }) });
}
export async function reviewMilestone(id: string, approve: boolean, note?: string) {
  if (!API_URL || !ADMIN_TOKEN) return;
  await adminFetch(`/admin/milestones/${id}/review`, { method: "POST", body: JSON.stringify({ approve, note }) });
}

const ago = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

// Sample data shaped like the API, so the console can be designed and demoed before the agents exist.
const sample: Omit<AdminData, "sampleReason"> = {
  queue: [
    { id: "s-p1", title: "Community Solar Kiosk", category: "Environment", region: "East Africa", status: "pending_review", goal: 400000, raised: 0, currency: "USD", frozen: false },
    { id: "s-p2", title: "Night School Lamps", category: "Education", region: "South Asia", status: "pending_review", goal: 150000, raised: 0, currency: "USD", frozen: false },
  ],
  cases: [
    {
      id: "s-c1",
      projectId: "girls-stem-club",
      projectTitle: "Girls' STEM Club",
      rule: "new_payer_burst",
      evidence: { new_payers: 20, window_minutes: 12, typical_amount_cents: 500, donor_ids: "20 accounts" },
      status: "open",
      createdAt: ago(2),
    },
  ],
  milestones: [
    { id: "s-m1", seq: 2, title: "Kaptembwo Desks: 40 desks delivered", amount: 120000, match: 30200, currency: "USD", dueDate: null, status: "held" },
  ],
  audit: [
    { id: "s-a1", actor: "giving_agent", action: "donation_requested", inputs: { mandate_id: 3, project: "Kaptembwo Desks", amount_cents: 300 }, ruleResult: "passed", reason: "4 backers, 6% funded, receipts uploaded", createdAt: ago(1) },
    { id: "s-a2", actor: "giving_agent", action: "project_skipped", inputs: { mandate_id: 3, project: "Lupus Patient Support Fund" }, ruleResult: "excluded_category", reason: "Outside the donor's chosen categories (education)", createdAt: ago(1) },
    { id: "s-a3", actor: "watchdog", action: "matching_frozen", inputs: { project: "Girls' STEM Club", rule: "new_payer_burst" }, ruleResult: "hit", reason: "20 new payer IDs gave similar small amounts within 12 minutes", createdAt: ago(2) },
    { id: "s-a4", actor: "milestone_agent", action: "tranche_held", inputs: { milestone_id: 7, receipt_total_cents: 135000, tranche_cents: 120000 }, ruleResult: "receipt_over_10pct", reason: "Receipt total is 12.5% above the tranche; sent to an admin", createdAt: ago(5) },
  ],
};
