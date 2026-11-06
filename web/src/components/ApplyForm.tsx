"use client";

import Link from "next/link";
import { useState } from "react";
import { saveOwner } from "@/lib/owner-tokens";
import { Banner, notify } from "./Status";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const field = "min-h-11 w-full border border-line bg-white px-3 text-sm text-ink";
type Row = { title: string; dollars: string; due: string };
type Done = { projectId: string; token: string; title: string };

const MESSAGES: Record<string, string> = {
  MILESTONES_DONT_ADD_UP: "The milestones must add up to the goal.",
  CATEGORY_NOT_FOUND: "That category no longer exists. Pick another.",
};

// Apply for funding: POST /projects. The project stays hidden until an admin verifies it.
export function ApplyForm({ categories }: { categories: { apiId: number; name: string }[] }) {
  const [f, setF] = useState({ title: "", facilitator: "", summary: "", category_id: String(categories[0]?.apiId ?? ""), goal: "", cause: "", group: "", region: "", hide: false, urgency: "3", tags: "", email: "" });
  const [rows, setRows] = useState<Row[]>([{ title: "", dollars: "", due: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [copied, setCopied] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });

  const goal = Math.round(Number(f.goal || 0) * 100);
  const total = rows.reduce((s, r) => s + Math.round(Number(r.dollars || 0) * 100), 0);
  const rowsOk = rows.length > 0 && rows.every((r) => r.title.trim() && Number(r.dollars) > 0 && r.due);
  const addsUp = goal > 0 && total === goal;
  const ready = f.title.trim() && f.summary.trim() && f.category_id && addsUp && rowsOk;
  const money = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(c / 100);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || !API_URL) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        title: f.title.trim(),
        facilitator: f.facilitator.trim() || undefined,
        summary: f.summary.trim(),
        category_id: Number(f.category_id),
        goal_cents: goal,
        tags: f.tags.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean),
        cause: f.cause.trim() || undefined,
        beneficiary_group: f.group || undefined,
        region: f.region.trim() || undefined,
        hide_location: f.hide,
        urgency: Number(f.urgency),
        payout_email: f.email.trim() || undefined,
        milestones: rows.map((r) => ({ title: r.title.trim(), amount_cents: Math.round(Number(r.dollars) * 100), due_date: r.due })),
      };
      const res = await fetch(`${API_URL}/projects`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) {
        const code = d?.detail?.error as string | undefined;
        // Field errors (422 from validation): name each field in words
        const fieldErrors = Array.isArray(d?.detail)
          ? (d.detail as { loc: (string | number)[]; msg: string }[]).map((x) => {
              const [, a, i, b] = x.loc;
              const name = a === "milestones" ? `Milestone ${Number(i) + 1} ${String(b ?? "").replace("_", " ")}` : String(a).replace("_", " ");
              return `${name}: ${x.msg.toLowerCase()}`;
            })
          : [];
        throw new Error((code && MESSAGES[code]) || d?.detail?.message || (fieldErrors.length ? fieldErrors.join("; ") : `Couldn't send (${res.status}).`));
      }
      const projectId = String(d.project_id);
      saveOwner(projectId, {
        token: d.owner_token,
        title: body.title,
        milestones: (d.milestone_ids as number[]).map((id, i) => ({ id, title: body.milestones[i].title, amount_cents: body.milestones[i].amount_cents })),
        savedAt: new Date().toISOString(),
      });
      setDone({ projectId, token: d.owner_token, title: body.title });
      notify("Application sent. An admin will check it before it's listed.", "success");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (done)
    return (
      <div className="mx-auto max-w-2xl space-y-5 bg-white p-6 shadow-[0_10px_30px_rgba(11,46,51,0.08)]">
        <h2 className="text-3xl">Application sent</h2>
        <p>
          <strong>{done.title}</strong> is waiting for an admin to check it (status: pending review). It isn&apos;t public until then.
        </p>
        <Banner tone="warning" title="Save your project token now">
          You need it to upload receipts and photos. It is shown <strong>only once</strong> and can&apos;t be shown again. We also saved it in this browser.
        </Banner>
        <div className="flex flex-wrap items-center gap-2">
          <code className="flex-1 break-all border border-line bg-surface-alt p-3 text-sm text-ink">{done.token}</code>
          <button
            type="button"
            className="btn btn-2 !min-h-11"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(done.token);
                setCopied(true);
              } catch {
                notify("Couldn't copy. Select the token and copy it by hand.", "error");
              }
            }}
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
        <Link href={`/projects/${done.projectId}/evidence`} className="btn">
          Go to evidence uploads
        </Link>
      </div>
    );

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl space-y-8 bg-white p-6 shadow-[0_10px_30px_rgba(11,46,51,0.08)] sm:p-8">
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 font-display text-2xl text-ink">Your project</legend>
        <label className="text-sm text-ink sm:col-span-2">
          Project name *
          <input required value={f.title} onChange={set("title")} className={field} placeholder="Mama Lishe Kitchen" />
        </label>
        <label className="text-sm text-ink">
          Group running it
          <input value={f.facilitator} onChange={set("facilitator")} className={field} placeholder="Kibera Women's Group" />
        </label>
        <label className="text-sm text-ink">
          Category *
          <select value={f.category_id} onChange={set("category_id")} className={field}>
            {categories.map((c) => (
              <option key={c.apiId} value={c.apiId}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-ink sm:col-span-2">
          What it does *
          <textarea required value={f.summary} onChange={set("summary")} rows={3} className={`${field} py-2`} placeholder="A school kitchen serving lunch to 200 pupils." />
        </label>
        <label className="text-sm text-ink">
          Cause
          <input value={f.cause} onChange={set("cause")} className={field} placeholder="nutrition" />
        </label>
        <label className="text-sm text-ink">
          Who it helps
          <select value={f.group} onChange={set("group")} className={field}>
            <option value="">Not specified</option>
            <option value="children">Children</option>
            <option value="adults">Adults</option>
            <option value="elderly">Elderly</option>
          </select>
        </label>
        <label className="text-sm text-ink">
          Place
          <input value={f.region} onChange={set("region")} className={field} placeholder="Nairobi" />
        </label>
        <label className="text-sm text-ink">
          Urgency (1 low – 5 urgent)
          <select value={f.urgency} onChange={set("urgency")} className={field}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-ink">
          Tags (comma-separated)
          <input value={f.tags} onChange={set("tags")} className={field} placeholder="food, schools" />
        </label>
        <label className="flex items-center gap-2 self-end text-sm text-ink">
          <input type="checkbox" checked={f.hide} onChange={set("hide")} className="size-5" /> Hide the exact place (for safety)
        </label>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-2 font-display text-2xl text-ink">Goal and milestones</legend>
        <p className="text-sm">Money is released step by step against receipts and photos. The milestones must add up exactly to the goal.</p>
        <label className="block max-w-xs text-sm text-ink">
          Goal ($) *
          <input required type="number" min="1" step="0.01" value={f.goal} onChange={set("goal")} className={field} />
        </label>
        <ol className="space-y-2">
          {rows.map((r, i) => (
            <li key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_130px_160px_auto]">
              <label className="text-sm text-ink">
                Milestone {i + 1}
                <input value={r.title} onChange={(e) => setRows(rows.map((x, k) => (k === i ? { ...x, title: e.target.value } : x)))} className={field} placeholder="Stoves" />
              </label>
              <label className="text-sm text-ink">
                Amount ($)
                <input type="number" min="0.01" step="0.01" value={r.dollars} onChange={(e) => setRows(rows.map((x, k) => (k === i ? { ...x, dollars: e.target.value } : x)))} className={field} />
              </label>
              <label className="text-sm text-ink">
                Due date *
                <input type="date" required value={r.due} onChange={(e) => setRows(rows.map((x, k) => (k === i ? { ...x, due: e.target.value } : x)))} className={field} />
              </label>
              <button type="button" onClick={() => setRows(rows.filter((_, k) => k !== i))} disabled={rows.length === 1} className="min-h-11 border border-line px-3 text-sm text-ink disabled:opacity-40" aria-label={`Remove milestone ${i + 1}`}>
                Remove
              </button>
            </li>
          ))}
        </ol>
        <button type="button" onClick={() => setRows([...rows, { title: "", dollars: "", due: "" }])} className="min-h-11 border border-primary px-4 text-sm font-medium text-primary">
          + Add a milestone
        </button>
        <p role="status" className={`border-l-4 p-3 text-sm ${addsUp ? "border-growth bg-surface-alt text-ink" : "border-cat-education bg-surface-alt text-ink"}`}>
          Milestones add up to <strong className="tabular">{money(total)}</strong> of <strong className="tabular">{money(goal)}</strong>
          {goal > 0 && !addsUp && <> · {total < goal ? `${money(goal - total)} still to assign` : `${money(total - goal)} too much`}</>}
          {addsUp && " ✓"}
        </p>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="mb-2 font-display text-2xl text-ink">Payouts (optional)</legend>
        <label className="block max-w-md text-sm text-ink">
          PayPal email for payouts
          <input type="email" value={f.email} onChange={set("email")} className={field} placeholder="kitchen@example.com" />
        </label>
      </fieldset>

      {error && <Banner tone="error">{error}</Banner>}
      {!API_URL && <Banner tone="info">Applications need the core API (NEXT_PUBLIC_API_URL).</Banner>}
      <button className="btn disabled:opacity-50" disabled={!ready || busy || !API_URL}>
        {busy ? "Sending…" : "Send application"}
      </button>
      {!ready && <p className="text-sm">The button turns on when the name, description, every milestone (name, amount, due date) and the total match the goal.</p>}
    </form>
  );
}
