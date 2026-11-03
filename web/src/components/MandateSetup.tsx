"use client";

import { useEffect, useState } from "react";
import type { Category } from "@/lib/types";
import { DonatePanel } from "./DonatePanel";
import { categoryIcon, Icon } from "./Icon";

// Giving Agent setup (#23). The donor's rules (mandate) are enforced by the core API, never by the
// agent: GET/PUT /donors/{id}/mandate, PATCH /donors/{id} for interests, pending approvals, agent runs.
// No login yet: the demo donor's id comes from NEXT_PUBLIC_DEMO_DONOR_ID.

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const DONOR_ID = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1";

type Mandate = {
  monthly_budget_cents: number;
  categories: number[];
  excluded_tags: string[];
  per_project_max_cents: number;
  approval_threshold_cents: number;
  weight_overrides: Record<string, number> | null;
  active: boolean;
  funded_balance_cents?: number;
  currency?: string;
};
type Pending = { donation_id: number; project_title: string; amount_cents: number; reason: string };
type Run = { id: number; run_at: string; report_text: string | null };

const STEPS = ["Your interests", "Your rules", "Review and fund"];
const GROUPS = ["Children", "Youth", "Adults", "Elderly", "Community"];

async function call<T>(path: string, init?: RequestInit): Promise<{ ok: true; data: T } | { ok: false; status: number; message: string }> {
  try {
    const r = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json" } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return { ok: false, status: r.status, message: d?.detail?.message ?? `Request failed (${r.status})` };
    return { ok: true, data: d as T };
  } catch {
    return { ok: false, status: 0, message: "Can't reach the server. Check your connection and try again." };
  }
}

export function MandateSetup({ categories, tags }: { categories: Category[]; tags: string[] }) {
  const live = Boolean(API_URL);
  const [step, setStep] = useState(0);
  const [cats, setCats] = useState<string[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [overlooked, setOverlooked] = useState(true);
  const [budget, setBudget] = useState("20");
  const [perProject, setPerProject] = useState("5");
  const [threshold, setThreshold] = useState("10");
  const [excluded, setExcluded] = useState<string[]>([]);
  const [balance, setBalance] = useState<number | null>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [donorMissing, setDonorMissing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  // Load what the donor already set up
  useEffect(() => {
    if (!live) return;
    (async () => {
      const donor = await call<{ interests: { categories?: string[]; groups?: string[]; overlooked?: boolean } | null }>(`/donors/${DONOR_ID}`);
      if (!donor.ok) {
        if (donor.status === 404) setDonorMissing(true);
        return;
      }
      const i = donor.data.interests ?? {};
      if (i.groups) setGroups(i.groups);
      if (typeof i.overlooked === "boolean") setOverlooked(i.overlooked);
      const m = await call<Mandate>(`/donors/${DONOR_ID}/mandate`);
      if (m.ok) {
        setCats(categories.filter((c) => c.apiId !== undefined && m.data.categories.includes(c.apiId)).map((c) => c.id));
        setBudget(String(m.data.monthly_budget_cents / 100));
        setPerProject(String(m.data.per_project_max_cents / 100));
        setThreshold(String(m.data.approval_threshold_cents / 100));
        setExcluded(m.data.excluded_tags ?? []);
        setBalance(m.data.funded_balance_cents ?? null);
      } else if (i.categories) setCats(i.categories);
      const p = await call<Pending[]>(`/donors/${DONOR_ID}/pending-approvals`);
      if (p.ok) setPending(p.data);
      const r = await call<Run[]>(`/donors/${DONOR_ID}/mandate/runs`);
      if (r.ok) setRuns(r.data.slice(0, 5));
    })();
  }, [live, categories]);

  const cents = (v: string) => Math.round(Number(v) * 100);
  const errors = {
    cats: cats.length === 0 ? "Choose at least one cause." : null,
    budget: !(cents(budget) >= 100) ? "Enter a monthly budget of at least $1." : null,
    perProject:
      !(cents(perProject) >= 100) ? "Enter at least $1." : cents(perProject) > cents(budget) ? "Can't be more than your monthly budget." : null,
    threshold: !(cents(threshold) >= 0) ? "Enter $0 or more." : null,
  };
  const stepOk = [!errors.cats, !errors.budget && !errors.perProject && !errors.threshold, true];
  const fmt = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(c / 100);

  async function save() {
    setSaving(true);
    setNotice(null);
    if (!live) {
      setNotice({ ok: true, text: "Saved in sample mode (nothing sent). Connect the API to save for real." });
      setSaving(false);
      return;
    }
    const d = await call(`/donors/${DONOR_ID}`, { method: "PATCH", body: JSON.stringify({ interests: { categories: cats, groups, overlooked } }) });
    const m = d.ok
      ? await call<Mandate>(`/donors/${DONOR_ID}/mandate`, {
          method: "PUT",
          body: JSON.stringify({
            monthly_budget_cents: cents(budget),
            categories: categories.filter((c) => cats.includes(c.id) && c.apiId !== undefined).map((c) => c.apiId),
            excluded_tags: excluded,
            per_project_max_cents: cents(perProject),
            approval_threshold_cents: cents(threshold),
            // API weights out of 100 (default few_backers 35, may move by up to 20)
            weight_overrides: overlooked ? { few_backers: 50 } : null,
            active: true,
          }),
        })
      : d;
    setSaving(false);
    if (m.ok) {
      setBalance((m.data as Mandate).funded_balance_cents ?? null);
      setNotice({ ok: true, text: "Your Giving Agent is set up. It will donate within these rules on its next run." });
    } else setNotice({ ok: false, text: m.message });
  }

  async function decide(id: number, approve: boolean) {
    const r = await call(`/donors/${DONOR_ID}/pending-approvals/${id}`, { method: "POST", body: JSON.stringify({ approve }) });
    if (r.ok) setPending((p) => p.filter((x) => x.donation_id !== id));
    setNotice(r.ok ? { ok: true, text: approve ? "Gift approved." : "Gift declined: no money moved." } : { ok: false, text: r.message });
  }

  const money = (label: string, value: string, set: (v: string) => void, error: string | null, help: string, id: string) => (
    <label htmlFor={id} className="flex flex-col gap-1 text-sm text-ink">
      <span className="font-medium">{label}</span>
      <span className="flex items-center border border-line bg-white focus-within:border-primary">
        <span className="px-3" aria-hidden>
          $
        </span>
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min="0"
          step="1"
          value={value}
          onChange={(e) => set(e.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={`${id}-help`}
          className="min-h-12 flex-1 bg-transparent pr-3 focus:outline-none"
        />
      </span>
      <span id={`${id}-help`} className={error ? "font-medium text-danger" : "text-text"}>
        {error ?? help}
      </span>
    </label>
  );

  return (
    <div className="grid gap-10 lg:grid-cols-[1.5fr_1fr]">
      <div className="space-y-6">
        {!live && (
          <p className="border-l-4 border-growth bg-white p-3 text-sm text-ink">Sample mode: connect the core API to save your Giving Agent for real.</p>
        )}
        {donorMissing && (
          <p role="alert" className="border-l-4 border-danger bg-white p-3 text-sm text-ink">
            The demo donor (id {DONOR_ID}) doesn&apos;t exist in the API yet, so this can&apos;t be saved. Person 1: add a demo donor to the seed.
          </p>
        )}

        <ol className="flex flex-wrap gap-2" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => i <= step && setStep(i)}
                aria-current={step === i ? "step" : undefined}
                className={`flex min-h-11 items-center gap-2 border px-4 text-sm ${
                  step === i ? "border-primary bg-primary text-white" : i < step ? "border-primary bg-white text-primary" : "border-line bg-white text-text"
                }`}
              >
                <span className="tabular font-bold">{i < step ? "✓" : i + 1}</span> {s}
              </button>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <div className="space-y-6 border border-line bg-white p-6">
            <fieldset>
              <legend className="mb-1 font-display text-xl text-ink">What do you care about?</legend>
              <p className="mb-3 text-sm">Your agent only gives to verified projects in these causes.</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {categories.map((c) => {
                  const on = cats.includes(c.id);
                  return (
                    <button
                      key={c.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setCats((x) => (on ? x.filter((y) => y !== c.id) : [...x, c.id]))}
                      className={`flex min-h-24 flex-col items-center justify-center gap-2 border p-3 ${on ? "border-primary bg-primary-container text-ink" : "border-line text-ink hover:border-primary"}`}
                    >
                      <Icon name={categoryIcon[c.id] ?? "heart"} size={30} className="text-primary" />
                      {c.name}
                    </button>
                  );
                })}
              </div>
              {errors.cats && <p className="mt-2 text-sm font-medium text-danger">{errors.cats}</p>}
            </fieldset>
            <fieldset>
              <legend className="mb-3 font-display text-xl text-ink">Who would you like to help? (optional)</legend>
              <div className="flex flex-wrap gap-2">
                {GROUPS.map((g) => {
                  const on = groups.includes(g);
                  return (
                    <button
                      key={g}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setGroups((x) => (on ? x.filter((y) => y !== g) : [...x, g]))}
                      className={`min-h-11 border px-4 text-sm ${on ? "border-primary bg-primary text-white" : "border-line text-ink hover:border-primary"}`}
                    >
                      {g}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <label className="flex items-start gap-3 text-ink">
              <input type="checkbox" checked={overlooked} onChange={(e) => setOverlooked(e.target.checked)} className="mt-1 size-5 accent-[#007190]" />
              <span>
                <span className="font-medium">Favour overlooked projects</span>
                <span className="block text-sm text-text">Give more weight to projects with few backers.</span>
              </span>
            </label>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-6 border border-line bg-white p-6">
            <div className="grid gap-5 sm:grid-cols-3">
              {money("Monthly budget", budget, setBudget, errors.budget, "The most your agent gives in a month.", "budget")}
              {money("Most per project", perProject, setPerProject, errors.perProject, "Spreads your gifts out.", "per-project")}
              {money("Ask me above", threshold, setThreshold, errors.threshold, "Bigger gifts wait for your yes.", "threshold")}
            </div>
            <fieldset>
              <legend className="mb-1 font-medium text-ink">Never fund projects tagged</legend>
              <p className="mb-3 text-sm">Your agent skips these, and tells you when it does.</p>
              <div className="flex flex-wrap gap-2">
                {tags.map((t) => {
                  const on = excluded.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setExcluded((x) => (on ? x.filter((y) => y !== t) : [...x, t]))}
                      className={`min-h-11 border px-4 text-sm ${on ? "border-ink bg-ink text-white line-through" : "border-line text-ink hover:border-primary"}`}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4 border border-line bg-white p-6">
            <h2 className="text-2xl">Your Giving Agent will…</h2>
            <ul className="space-y-2 text-ink">
              <li>
                give up to <strong>{fmt(cents(budget))}</strong> a month to{" "}
                <strong>{categories.filter((c) => cats.includes(c.id)).map((c) => c.name).join(", ")}</strong>
                {groups.length > 0 && <> projects helping <strong>{groups.join(", ").toLowerCase()}</strong></>}
              </li>
              <li>
                give at most <strong>{fmt(cents(perProject))}</strong> to any one project
                {overlooked && ", favouring projects with few backers"}
              </li>
              <li>
                ask you first before any gift over <strong>{fmt(cents(threshold))}</strong>
              </li>
              {excluded.length > 0 && (
                <li>
                  never fund projects tagged <strong>{excluded.join(", ")}</strong>
                </li>
              )}
              <li>explain every choice in your impact report</li>
            </ul>
            <p className="text-sm">The platform checks every gift against these rules before any money moves, so the agent can&apos;t overspend.</p>
            <button type="button" onClick={save} disabled={saving || donorMissing} className="btn btn-2 w-full sm:w-auto">
              {saving ? "Saving…" : "Save my Giving Agent"}
            </button>
          </div>
        )}

        {notice && (
          <p role={notice.ok ? "status" : "alert"} className={`border-l-4 bg-white p-3 text-sm text-ink ${notice.ok ? "border-growth" : "border-danger"}`}>
            {notice.ok ? "✓ " : ""}
            {notice.text}
          </p>
        )}

        <div className="flex justify-between gap-3">
          <button
            type="button"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="min-h-12 border border-line bg-white px-5 text-ink disabled:invisible"
          >
            Back
          </button>
          {step < 2 && (
            <button type="button" onClick={() => setStep((s) => s + 1)} disabled={!stepOk[step]} className="btn btn-2 disabled:opacity-50">
              Next
            </button>
          )}
        </div>
      </div>

      <aside className="h-fit space-y-6 lg:sticky lg:top-28">
        <div className="space-y-3 border border-line bg-white p-6">
          <h2 className="text-2xl">Fund your agent</h2>
          <p className="text-sm">
            Top up once through PayPal; your agent gives from this balance.
            {balance !== null && (
              <>
                {" "}
                Balance now: <strong className="text-ink">{fmt(balance)}</strong>.
              </>
            )}
          </p>
          <DonatePanel projectTitle="your Giving Agent budget" target={{ kind: "AGENT" }} />
        </div>

        <div className="space-y-3 border border-line bg-white p-6">
          <h2 className="text-xl">Waiting for your yes</h2>
          {pending.length === 0 ? (
            <p className="text-sm">Nothing waiting. Gifts above your limit appear here before any money moves.</p>
          ) : (
            pending.map((p) => (
              <div key={p.donation_id} className="space-y-2 border-t border-line pt-3">
                <p className="text-ink">
                  <strong>{fmt(p.amount_cents)}</strong> to {p.project_title}
                </p>
                <p className="text-sm">{p.reason}</p>
                <div className="flex gap-2">
                  <button type="button" onClick={() => decide(p.donation_id, true)} className="min-h-11 bg-primary px-4 text-sm font-medium text-white">
                    Approve
                  </button>
                  <button type="button" onClick={() => decide(p.donation_id, false)} className="min-h-11 border border-line px-4 text-sm text-ink">
                    Decline
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="space-y-3 border border-line bg-white p-6">
          <h2 className="text-xl">What your agent did</h2>
          {runs.length === 0 ? (
            <p className="text-sm">No runs yet. After each run you&apos;ll see what it gave, what it skipped and why.</p>
          ) : (
            runs.map((r) => (
              <div key={r.id} className="border-t border-line pt-3 text-sm">
                <p className="font-medium text-ink">{new Date(r.run_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</p>
                <p>{r.report_text ?? "Run recorded."}</p>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}
