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

export type Dashboard = {
  totals: {
    received: number;
    refunded: number;
    fees: number;
    paidOut: number;
    released: number;
    releasedNotPaid: number;
    agentUnspent: number;
    platformBalance: number;
  } | null;
  issues: { check: string; severity: "error" | "warning"; detail: string; count: number }[];
  reconciledAt: string | null;
  payouts: { batch: string; status: string; amount: number; items: number; pending: number }[];
};

/** Money figures for the overview: reconciliation totals + issues, and payout batches */
export async function getDashboard(): Promise<Dashboard> {
  const empty: Dashboard = { totals: null, issues: [], reconciledAt: null, payouts: [] };
  if (!API_URL || !ADMIN_TOKEN) return empty;
  const [rec, pay] = await Promise.all([
    adminFetch<{ generated_at: string; totals: Record<string, number>; issues: { check: string; severity: "error" | "warning"; detail: string; refs: unknown[] }[] }>("/admin/reconciliation").catch(() => null),
    adminFetch<{ sender_batch_id: string; status: string; items: { amount_cents: number; status: string }[] }[]>("/admin/payouts").catch(() => []),
  ]);
  const t = rec?.totals;
  return {
    totals: t
      ? {
          received: t.received_via_paypal_cents ?? 0,
          refunded: t.refunded_cents ?? 0,
          fees: t.paypal_fees_cents ?? 0,
          paidOut: t.paid_out_cents ?? 0,
          released: t.tranches_released_cents ?? 0,
          releasedNotPaid: t.released_not_yet_paid_cents ?? 0,
          agentUnspent: t.agent_budget_unspent_cents ?? 0,
          platformBalance: t.platform_balance_cents ?? 0,
        }
      : null,
    issues: (rec?.issues ?? []).map((i) => ({ check: i.check, severity: i.severity, detail: i.detail, count: i.refs?.length ?? 1 })),
    reconciledAt: rec?.generated_at ?? null,
    payouts: pay.map((b) => ({
      batch: b.sender_batch_id,
      status: b.status,
      amount: b.items.reduce((s, i) => s + i.amount_cents, 0),
      items: b.items.length,
      pending: b.items.filter((i) => i.status !== "SUCCESS").length,
    })),
  };
}

// ---- Rounds (#2) ----
export type RoundInfo = {
  id: number;
  name: string;
  startsAt: string;
  endsAt: string;
  pool: number;
  currency: string;
  projectCapPct: number;
  floorPct: number;
  perPersonCap: number;
  status: "scheduled" | "open" | "closing" | "closed";
};
type ApiRoundFull = { id: number; name: string; starts_at: string; ends_at: string; matching_pool_cents: number; currency: string; project_cap_pct: number; floor_pct: number; per_person_cap_cents: number; status: RoundInfo["status"] };
const toRound = (r: ApiRoundFull): RoundInfo => ({
  id: r.id,
  name: r.name,
  startsAt: r.starts_at,
  endsAt: r.ends_at,
  pool: r.matching_pool_cents,
  currency: r.currency,
  projectCapPct: r.project_cap_pct,
  floorPct: r.floor_pct,
  perPersonCap: r.per_person_cap_cents,
  status: r.status,
});

export async function listRounds(): Promise<RoundInfo[]> {
  if (!API_URL) return [];
  const res = await fetch(`${API_URL}/rounds`, { cache: "no-store" });
  return res.ok ? ((await res.json()) as ApiRoundFull[]).map(toRound) : [];
}

export type RoundFields = { name?: string; starts_at?: string; ends_at?: string; matching_pool_cents?: number; project_cap_pct?: number; floor_pct?: number; per_person_cap_cents?: number };
export async function createRound(body: RoundFields) {
  return toRound(await adminFetch<ApiRoundFull>("/admin/rounds", { method: "POST", body: JSON.stringify(body) }));
}
export async function updateRound(id: number, body: RoundFields) {
  return toRound(await adminFetch<ApiRoundFull>(`/admin/rounds/${id}`, { method: "PATCH", body: JSON.stringify(body) }));
}
export async function closeRound(id: number) {
  await adminFetch(`/admin/rounds/${id}/close?early=true`, { method: "POST" });
}

// ---- Applications and evidence (#3) ----
export type ProjectDocument = { id: number; kind: string; fileUrl: string; milestoneId: number | null; flags: string[] };
export async function getProjectDocuments(projectId: string): Promise<ProjectDocument[]> {
  if (!API_URL || !ADMIN_TOKEN) return [];
  const docs = await adminFetch<{ id: number; kind: string; file_url: string; milestone_id: number | null; flags: string[] | null }[]>(`/admin/projects/${projectId}/documents`).catch(() => []);
  return docs.map((d) => ({ id: d.id, kind: d.kind, fileUrl: d.file_url, milestoneId: d.milestone_id, flags: d.flags ?? [] }));
}
export async function newOwnerToken(projectId: string) {
  return (await adminFetch<{ owner_token: string }>(`/admin/projects/${projectId}/owner-token`, { method: "POST" })).owner_token;
}

// ---- Refunds (#5) ----
export type DonationInfo = { id: number; amount: number; currency: string; status: string; targetType: string; projectId: number | null; captureId: string | null; capturedAt: string | null };
export async function getDonation(id: number): Promise<DonationInfo> {
  const d = await adminFetch<{ id: number; amount_cents: number; currency: string; status: string; target_type: string; project_id: number | null; paypal_capture_id: string | null; captured_at: string | null }>(`/donations/${id}`);
  return { id: d.id, amount: d.amount_cents, currency: d.currency, status: d.status, targetType: d.target_type, projectId: d.project_id, captureId: d.paypal_capture_id, capturedAt: d.captured_at };
}
export type RefundResult = { donation_id: number; refund_id: string; paypal_status: string; amount_cents: number; refunded_total_cents: number; donation_status: string };
export async function refundDonation(id: number, reason: string, amountCents?: number) {
  return adminFetch<RefundResult>(`/admin/donations/${id}/refund`, { method: "POST", body: JSON.stringify({ reason, ...(amountCents ? { amount_cents: amountCents } : {}) }) });
}

// ---- Agent kill switch and audit hash chain ----
export type AgentStatus = { paused: boolean; reason: string | null; since: string | null; updatedBy: string | null; sample?: boolean };
type ApiStatus = { paused: boolean; reason?: string | null; since?: string | null; updated_by?: string | null };
const toStatus = (s: ApiStatus): AgentStatus => ({ paused: s.paused, reason: s.reason ?? null, since: s.since ?? null, updatedBy: s.updated_by ?? null });

export async function getAgentStatus(): Promise<AgentStatus> {
  if (!API_URL || !ADMIN_TOKEN) return { paused: false, reason: null, since: null, updatedBy: null, sample: true };
  return toStatus(await adminFetch<ApiStatus>("/admin/agents/status"));
}
export async function pauseAgents(reason?: string) {
  if (!API_URL || !ADMIN_TOKEN) return;
  await adminFetch("/admin/agents/pause", { method: "POST", body: JSON.stringify({ reason: reason?.trim() || "Paused from the admin console" }) });
}
export async function resumeAgents(reason?: string) {
  if (!API_URL || !ADMIN_TOKEN) return;
  await adminFetch("/admin/agents/resume", { method: "POST", body: JSON.stringify({ reason: reason?.trim() || "Resumed from the admin console" }) });
}

export type ChainCheck = { valid: boolean; checked: number; firstBadId: number | null; firstBadReason: string | null; headHash: string };
export async function verifyAuditChain(): Promise<ChainCheck> {
  if (!API_URL || !ADMIN_TOKEN) return { valid: true, checked: 0, firstBadId: null, firstBadReason: "Sample mode: nothing to check.", headHash: "" };
  const r = await adminFetch<{ valid: boolean; checked: number; first_bad_id: number | null; first_bad_reason: string | null; head_hash: string }>("/admin/audit-log/verify");
  return { valid: r.valid, checked: r.checked, firstBadId: r.first_bad_id, firstBadReason: r.first_bad_reason, headHash: r.head_hash };
}

export type ChainRow = { id: number; seq: number | null; actor: string; action: string; rule: string | null; hash: string | null; prevHash: string | null; createdAt: string };
export async function getAuditChain(limit = 100): Promise<ChainRow[]> {
  if (!API_URL || !ADMIN_TOKEN) return [];
  const rows = await adminFetch<{ id: number; seq?: number; actor: string; action: string; rule_result: string | null; hash?: string; prev_hash?: string; created_at: string }[]>(`/admin/audit-log?include_hash=true&limit=${limit}`);
  return rows.map((a) => ({ id: a.id, seq: a.seq ?? null, actor: a.actor, action: a.action, rule: a.rule_result, hash: a.hash ?? null, prevHash: a.prev_hash ?? null, createdAt: a.created_at }));
}

export async function resolveCaseRemoving(id: string, note?: string) {
  if (!API_URL || !ADMIN_TOKEN) return;
  await adminFetch(`/admin/cases/${id}/resolve`, { method: "POST", body: JSON.stringify({ action: "confirm", remove_project: true, note }) });
}
