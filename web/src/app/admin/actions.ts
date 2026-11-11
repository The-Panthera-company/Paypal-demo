"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";

// Defence in depth: the /admin password is checked by middleware for the page, and again here, so
// an admin action can't run from a request that didn't come with the admin login.
async function requireAdmin() {
  const password = process.env.ADMIN_UI_PASSWORD;
  if (!password) return;
  const [scheme, encoded] = ((await headers()).get("authorization") ?? "").split(" ");
  const given = scheme === "Basic" && encoded ? Buffer.from(encoded, "base64").toString().split(":").slice(1).join(":") : null;
  if (given !== password) throw new Error("Admin login required");
}
import { getPayoutEmail, setPayoutEmail, retryProcurement, reviewProcurement, getAuditChain, pauseAgents, resolveCaseRemoving, resumeAgents, verifyAuditChain, type ChainCheck, type ChainRow, closeRound, createRound, getDonation, newOwnerToken, refundDonation, resolveCase, reviewMilestone, updateRound, verifyProject, type DonationInfo, type RefundResult, type RoundFields } from "@/lib/admin";

export type ActionResult = { ok: true; message: string } | { ok: false; message: string };

async function run(fn: () => Promise<void>, done: string): Promise<ActionResult> {
  try {
    await fn();
    revalidatePath("/admin");
    return { ok: true, message: done };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Something went wrong." };
  }
}

export async function verifyAction(id: string, approve: boolean, note?: string) {
  await requireAdmin();
  return run(() => verifyProject(id, approve, note), approve ? "Project verified and listed." : "Project sent back to the applicant.");
}

export async function resolveCaseAction(id: string, action: "clear" | "confirm", note?: string) {
  await requireAdmin();
  return run(
    () => resolveCase(id, action, note),
    action === "clear" ? "Case cleared: matching resumes." : "Case confirmed: flagged donors now count as one person.",
  );
}

export async function reviewMilestoneAction(id: string, approve: boolean, note?: string) {
  await requireAdmin();
  return run(() => reviewMilestone(id, approve, note), approve ? "Tranche released for payout." : "Sent back: the project can upload new evidence.");
}

// ---- Rounds ----
export type RoundFormState = { ok: boolean; message: string } | null;

function roundFields(f: FormData, includeStart: boolean): RoundFields {
  const num = (k: string) => (f.get(k) ? Number(f.get(k)) : undefined);
  const iso = (k: string) => (f.get(k) ? new Date(String(f.get(k))).toISOString() : undefined);
  const dollars = num("pool");
  const cap = num("per_person_cap");
  return {
    name: String(f.get("name") ?? "").trim() || undefined,
    ...(includeStart ? { starts_at: iso("starts_at") } : {}),
    ends_at: iso("ends_at"),
    matching_pool_cents: dollars !== undefined ? Math.round(dollars * 100) : undefined,
    project_cap_pct: num("project_cap_pct"),
    floor_pct: num("floor_pct"),
    per_person_cap_cents: cap !== undefined ? Math.round(cap * 100) : undefined,
  };
}

export async function createRoundAction(_: RoundFormState, f: FormData): Promise<RoundFormState> {
  await requireAdmin();
  const r = await run(async () => {
    const round = await createRound(roundFields(f, true));
    if (!round) throw new Error("Not created");
  }, "Round scheduled. It opens by itself at its start time.");
  revalidatePath("/leaderboard");
  return r;
}

export async function updateRoundAction(_: RoundFormState, f: FormData): Promise<RoundFormState> {
  await requireAdmin();
  const id = Number(f.get("id"));
  const open = f.get("status") === "open";
  const body = roundFields(f, !open); // an open round can't change its start
  const r = await run(() => updateRound(id, body).then(() => undefined), "Round updated.");
  revalidatePath("/leaderboard");
  return r;
}

export async function closeRoundAction(id: number) {
  await requireAdmin();
  const r = await run(() => closeRound(id), "Round closed: final results are written and matching is added to each project's next milestone.");
  revalidatePath("/leaderboard");
  revalidatePath(`/rounds/${id}`);
  return r;
}

// ---- Applications ----
export async function newOwnerTokenAction(projectId: string): Promise<{ ok: true; token: string } | { ok: false; message: string }> {
  await requireAdmin();
  try {
    return { ok: true, token: await newOwnerToken(projectId) };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Couldn't make a new token." };
  }
}

// ---- Refunds ----
export async function lookupDonationAction(id: number): Promise<{ ok: true; donation: DonationInfo } | { ok: false; message: string }> {
  await requireAdmin();
  try {
    return { ok: true, donation: await getDonation(id) };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "No such donation." };
  }
}

export async function refundAction(id: number, reason: string, amountCents?: number): Promise<{ ok: true; result: RefundResult } | { ok: false; message: string }> {
  await requireAdmin();
  try {
    const result = await refundDonation(id, reason, amountCents);
    revalidatePath("/admin");
    return { ok: true, result };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Refund failed." };
  }
}

// ---- Kill switch, hash chain, collusion ----
export async function pauseAgentsAction(reason?: string) {
  await requireAdmin();
  const r = await run(() => pauseAgents(reason), "Agents paused: no money can move until you resume.");
  revalidatePath("/", "layout");
  return r;
}
export async function resumeAgentsAction() {
  await requireAdmin();
  const r = await run(() => resumeAgents(), "Agents resumed.");
  revalidatePath("/", "layout");
  return r;
}
export async function verifyChainAction(): Promise<{ ok: true; check: ChainCheck; rows: ChainRow[] } | { ok: false; message: string }> {
  await requireAdmin();
  try {
    const [check, rows] = await Promise.all([verifyAuditChain(), getAuditChain(100)]);
    return { ok: true, check, rows };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Couldn't verify the chain." };
  }
}
export async function confirmAndRemoveAction(id: string, note?: string) {
  await requireAdmin();
  return run(() => resolveCaseRemoving(id, note), "Case confirmed and the project removed; its donations are refunded.");
}

// ---- Procurement ----
export async function reviewProcurementAction(id: number, approve: boolean) {
  await requireAdmin();
  return run(() => reviewProcurement(id, approve), approve ? "Purchase approved. The agent pays the supplier on its next step." : "Purchase rejected.");
}
export async function retryProcurementAction(id: number) {
  await requireAdmin();
  return run(() => retryProcurement(id), "Payment sent again with the same PayPal batch.");
}

// ---- Payout email ----
export async function getPayoutEmailAction(projectId: string): Promise<{ ok: true; email: string | null } | { ok: false; message: string }> {
  await requireAdmin();
  try {
    return { ok: true, email: await getPayoutEmail(projectId) };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Couldn't read it." };
  }
}
export async function setPayoutEmailAction(projectId: string, email: string) {
  await requireAdmin();
  return run(() => setPayoutEmail(projectId, email.trim()), "PayPal payout email saved.");
}

// ---- Procurement Agent: run now (server-side; INTERNAL_TOKEN never reaches the browser) ----
export type ProcurementRunResult =
  | { ok: true; runs: { procurementId: number | null; runId: number | null; summary: string }[]; abstained: { procurementId: number | null; reason: string }[] }
  | { ok: false; message: string };
export async function runProcurementAgentAction(): Promise<ProcurementRunResult> {
  await requireAdmin();
  const agents = (process.env.AGENTS_INTERNAL_URL || process.env.NEXT_PUBLIC_AGENTS_URL)?.replace(/\/$/, "");
  const token = process.env.INTERNAL_TOKEN ?? "";
  if (!agents || !token) return { ok: false, message: "The agents service isn't connected (AGENTS URL and INTERNAL_TOKEN on the website's server)." };
  try {
    const r = await fetch(`${agents}/agents/procurement/run`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: "{}",
      signal: AbortSignal.timeout(120_000),
    });
    const d = (await r.json().catch(() => ({}))) as { runs?: Record<string, unknown>[]; abstained?: Record<string, unknown>[]; detail?: unknown };
    if (!r.ok) return { ok: false, message: typeof d.detail === "string" ? d.detail : `The Procurement Agent couldn't run (${r.status}).` };
    const num = (v: unknown) => (typeof v === "number" ? v : typeof v === "string" && /^\d+$/.test(v) ? Number(v) : null);
    const txt = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : JSON.stringify(v));
    revalidatePath("/admin");
    return {
      ok: true,
      runs: (d.runs ?? []).map((x) => ({
        procurementId: num(x.procurement_id ?? x.procurementId),
        runId: num(x.run_id ?? x.runId),
        summary: txt(x.summary ?? x.report_text ?? x.status ?? x.description),
      })),
      abstained: (d.abstained ?? []).map((x) => ({ procurementId: num(x.procurement_id ?? x.procurementId ?? x.id), reason: txt(x.reason ?? x.why ?? x.detail) })),
    };
  } catch {
    return { ok: false, message: "The agents service didn't answer. It may be waking up; try again in a minute." };
  }
}
