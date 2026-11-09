// Managed purchases (procurement). Browser-safe: public reads and the owner's request, which is
// authorised by the project token (X-Project-Token), never the admin token.
const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

export type ProcurementStatus = "requested" | "proposed" | "approved" | "paid" | "failed" | "cancelled";
export type LineItem = { description?: string; quantity?: number; unit_amount_cents?: number; amount_cents?: number };
export type Procurement = {
  id: number;
  project_id: number;
  milestone_id: number;
  description: string;
  quantity: number;
  max_amount_cents: number;
  currency: string;
  status: ProcurementStatus;
  supplier_name: string | null;
  amount_cents: number | null;
  line_items: LineItem[];
  rationale: string | null;
  admin_approved: boolean;
  payout_id: number | null;
  paypal_batch_id: string | null;
  receipt_url: string | null;
  needs_approval: boolean;
  error: string | null;
  created_at: string;
  updated_at: string;
  /** Agent run that proposed or paid it, if the API sends one */
  run_id?: number | null;
};

/** What the owner sees for each status (the API's "cancelled" reads as rejected) */
export const PROCUREMENT_LABEL: Record<ProcurementStatus, string> = {
  requested: "Requested",
  proposed: "Supplier proposed",
  approved: "Approved",
  paid: "Paid",
  failed: "Payment failed",
  cancelled: "Rejected",
};

const ERRORS: Record<string, string> = {
  BAD_PROJECT_TOKEN: "That project token isn't right. Check it, or ask an admin for a new one.",
  MILESTONE_NOT_OPEN: "This milestone isn't open for purchases.",
  AMOUNT_ABOVE_MILESTONE: "The most you can ask for is this milestone's amount plus its match.",
  PROCUREMENT_EXISTS: "This milestone already has a purchase in progress.",
};

export async function fetchProjectProcurements(projectId: string | number, init?: RequestInit): Promise<Procurement[]> {
  if (!API_URL) return [];
  const r = await fetch(`${API_URL}/projects/${projectId}/procurements`, { cache: "no-store", ...init });
  if (r.status === 404) return [];
  if (!r.ok) throw new Error(`Couldn't load purchases (${r.status})`);
  return r.json();
}

export async function requestPurchase(
  projectId: string,
  token: string,
  body: { milestone_id: number; description: string; quantity: number; max_amount_cents: number },
): Promise<Procurement> {
  const r = await fetch(`${API_URL}/projects/${projectId}/procurement-requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Project-Token": token },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const code = d?.detail?.error as string | undefined;
    throw new Error((code && ERRORS[code]) || d?.detail?.message || `Request failed (${r.status}).`);
  }
  return d as Procurement;
}

export const money = (cents: number | null | undefined, currency = "USD") =>
  cents == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);

/** "40 books bought" from the request, used on the project page */
export const boughtTitle = (p: Procurement) => {
  const d = p.description.trim();
  return /^\d/.test(d) ? `${d} bought` : `${p.quantity} × ${d} bought`;
};
