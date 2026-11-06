"use server";

// "Run now": asks Person 3's agents service to run the demo donor's Giving Agent. Server-only:
// the internal token never reaches the browser. The service decides and records; the rules
// engine checks every gift.
const AGENTS_URL = (process.env.AGENTS_INTERNAL_URL || process.env.NEXT_PUBLIC_AGENTS_URL)?.replace(/\/$/, "");
const INTERNAL_TOKEN = process.env.INTERNAL_TOKEN ?? "";
const API_URL = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL)?.replace(/\/$/, "");
const DONOR_ID = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1";

export type RunNowResult =
  | { ok: true; runId: number | null; message: string; chosen: { project_id: number; title?: string; amount_cents: number }[] }
  | { ok: false; message: string };

export async function runAgentNow(): Promise<RunNowResult> {
  if (!AGENTS_URL || !INTERNAL_TOKEN) return { ok: false, message: "The agents service isn't connected to this site yet (AGENTS URL and INTERNAL_TOKEN on the website's server)." };
  try {
    const m = await fetch(`${API_URL}/donors/${DONOR_ID}/mandate`, { cache: "no-store" });
    if (!m.ok) return { ok: false, message: "Set up your Giving Agent's rules first." };
    const mandate = (await m.json()) as { id: number };
    const r = await fetch(`${AGENTS_URL}/agents/giving/run`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${INTERNAL_TOKEN}` },
      body: JSON.stringify({ mandateId: mandate.id, force: true }),
      signal: AbortSignal.timeout(90_000),
    });
    const d = (await r.json().catch(() => ({}))) as { run_id?: number | null; report_text?: string; chosen?: { project_id: number; title?: string; amount_cents: number }[]; detail?: string };
    if (!r.ok) return { ok: false, message: typeof d.detail === "string" ? d.detail : `The agent couldn't run (${r.status}).` };
    return {
      ok: true,
      runId: d.run_id ?? null,
      chosen: d.chosen ?? [],
      message: d.run_id ? "Run recorded. Here is what it did." : d.report_text ?? "The agent ran in dry-run mode: nothing was recorded.",
    };
  } catch {
    return { ok: false, message: "The agents service didn't answer. It may be waking up; try again in a minute." };
  }
}
