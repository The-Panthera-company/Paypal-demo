"use client";

import { useEffect, useRef, useState } from "react";
import type { Category } from "@/lib/types";
import { Banner } from "./Status";
import { BundiIcon } from "./BundiIcon";

// "Describe your giving in your own words": the agents service turns the words into a proposed
// mandate. The donor sees a field-by-field diff and decides. Accept only fills the wizard; the
// wizard's Save button is still the only thing that writes (PUT) the mandate.

const AGENTS_URL = process.env.NEXT_PUBLIC_AGENTS_URL?.replace(/\/$/, "");
const EXAMPLES = ["Girls' education in Kenya, no faith-based orgs, $20/month", "Clean water, $10 a month, $3 per project", "Ask me before any gift over $10"];

/** The wizard's values in its own units (dollars as strings, category slugs) */
export type DraftValues = { cats: string[]; budget: string; perProject: string; threshold: string; excluded: string[] };

type ApiDraft = {
  proposed?: Record<string, unknown>;
  mandate?: Record<string, unknown>;
  warnings?: (string | { message?: string })[];
  rejected?: (string | { text?: string; item?: string; value?: unknown; reason?: string })[];
  used_llm?: boolean;
};

const dollars = (c: unknown) => (typeof c === "number" && Number.isFinite(c) ? String(c / 100) : undefined);
const show$ = (v: string) => (v === "" ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(v)));

/** Map the API's proposal (cents, numeric category ids or names) onto the wizard's values */
function toValues(p: Record<string, unknown>, current: DraftValues, categories: Category[]): DraftValues {
  const cats = Array.isArray(p.categories)
    ? (p.categories as unknown[])
        .map((x) => categories.find((c) => c.apiId === x || c.id === x || (typeof x === "string" && c.name.toLowerCase() === x.toLowerCase()))?.id)
        .filter((x): x is string => !!x)
    : current.cats;
  return {
    cats,
    budget: dollars(p.monthly_budget_cents) ?? current.budget,
    perProject: dollars(p.per_project_max_cents) ?? current.perProject,
    threshold: dollars(p.approval_threshold_cents) ?? current.threshold,
    excluded: Array.isArray(p.excluded_tags) ? (p.excluded_tags as string[]) : current.excluded,
  };
}

type SR = { start(): void; stop(): void; lang: string; interimResults: boolean; onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };

export function MandateDraft({
  current,
  categories,
  onAccept,
  onEdit,
}: {
  current: DraftValues;
  categories: Category[];
  onAccept: (v: DraftValues) => void;
  onEdit: (v: DraftValues) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ values: DraftValues; warnings: string[]; rejected: string[]; usedLlm: boolean } | null>(null);
  const [canListen, setCanListen] = useState(false);
  const [listening, setListening] = useState(false);
  const rec = useRef<SR | null>(null);

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR };
    setCanListen(!!(w.SpeechRecognition ?? w.webkitSpeechRecognition));
  }, []);

  if (!AGENTS_URL)
    return <p className="border border-dashed border-line bg-white p-4 text-sm">Natural-language setup needs the agents service. Use the steps below instead.</p>;

  const listen = () => {
    const w = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) return;
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new Ctor();
    r.lang = navigator.language || "en-US";
    r.interimResults = false;
    r.onresult = (e) => setText((t) => `${t ? `${t} ` : ""}${e.results[0][0].transcript}`.trim());
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };

  async function submit() {
    setBusy(true);
    setError(null);
    setDraft(null);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 20_000);
    try {
      const res = await fetch(`${AGENTS_URL}/agents/mandate/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          text,
          current: {
            monthly_budget_cents: Math.round(Number(current.budget) * 100),
            per_project_max_cents: Math.round(Number(current.perProject) * 100),
            approval_threshold_cents: Math.round(Number(current.threshold) * 100),
            categories: categories.filter((c) => current.cats.includes(c.id)).map((c) => c.apiId ?? c.id),
            excluded_tags: current.excluded,
          },
        }),
      });
      if (res.status === 429) throw new Error("Too many tries in a short time. Wait a minute, or set your rules with the steps below.");
      if (res.status === 503) throw new Error("The agent can't read sentences right now. Set your rules with the steps below; nothing is lost.");
      if (!res.ok) throw new Error(`The agent couldn't read that (${res.status}). Try rewording, or use the steps below.`);
      const d = (await res.json()) as ApiDraft;
      const p = d.proposed ?? d.mandate ?? {};
      setDraft({
        values: toValues(p, current, categories),
        warnings: (d.warnings ?? []).map((w) => (typeof w === "string" ? w : w.message ?? "")).filter(Boolean),
        rejected: (d.rejected ?? []).map((r) => (typeof r === "string" ? r : [r.text ?? r.item ?? (r.value != null ? String(r.value) : ""), r.reason].filter(Boolean).join(": "))).filter(Boolean),
        usedLlm: d.used_llm !== false,
      });
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === "AbortError"
          ? "The agent took too long to answer. Set your rules with the steps below, or try again."
          : e instanceof TypeError
            ? "Can't reach the agents service. Set your rules with the steps below."
            : e instanceof Error
              ? e.message
              : "Something went wrong.",
      );
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }

  const name = (ids: string[]) => categories.filter((c) => ids.includes(c.id)).map((c) => c.name).join(", ") || "—";
  const rows = draft
    ? ([
        ["Causes", name(current.cats), name(draft.values.cats)],
        ["Monthly budget", show$(current.budget), show$(draft.values.budget)],
        ["Most per project", show$(current.perProject), show$(draft.values.perProject)],
        ["Ask me above", show$(current.threshold), show$(draft.values.threshold)],
        ["Never fund tags", current.excluded.join(", ") || "—", draft.values.excluded.join(", ") || "—"],
      ] as const)
    : [];
  const changed = rows.filter(([, a, b]) => a !== b);

  return (
    <section className="space-y-5 border-t-4 border-primary bg-white p-6 shadow-[0_10px_30px_rgba(11,46,51,0.08)] sm:p-8" aria-labelledby="nl-title">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center bg-[#fffaf2] text-[#6b4a3a] ring-1 ring-line"><BundiIcon size={34} /></span>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[2px] text-primary">Ask Bundi</p>
          <h2 id="nl-title" className="font-display text-2xl text-ink">Describe your giving in your own words</h2>
          <p className="mt-1 text-sm">Bundi drafts your rules; you see every change and decide. Nothing is saved until you press Save.</p>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-xs font-bold uppercase tracking-[2px] text-text">Try one</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((x) => (
            <button key={x} type="button" onClick={() => setText(x)} aria-pressed={text === x} className={`flex min-h-10 items-center gap-2 px-4 text-left text-sm transition-colors ${text === x ? "bg-ink text-white" : "bg-surface-alt text-ink hover:bg-primary-container"}`}>
              <span aria-hidden className={text === x ? "text-accent" : "text-primary"}>✦</span>
              {x}
            </button>
          ))}
        </div>
      </div>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) submit();
        }}
      >
        <label className="sr-only" htmlFor="nl-text">
          Your giving in your own words
        </label>
        <textarea id="nl-text" value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={1000} className="field w-full p-4 text-ink" placeholder="e.g. Clean water and girls' education, $15 a month, ask me before anything over $5" />
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-2 disabled:opacity-50" disabled={busy || !text.trim()}>
            {busy ? "Reading…" : "Draft my rules"}
          </button>
          {canListen && (
            <button type="button" onClick={listen} aria-pressed={listening} className={`flex min-h-12 items-center gap-2 border px-4 text-sm font-medium ${listening ? "border-cat-health bg-cat-health text-white" : "border-line bg-white text-ink hover:border-primary"}`}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M5 11a7 7 0 0014 0M12 18v3" />
              </svg>
              {listening ? "Listening… tap to stop" : "Speak"}
            </button>
          )}
        </div>
      </form>

      {error && <Banner tone="error">{error}</Banner>}

      {draft && (
        <div className="space-y-3 bg-white p-4" role="region" aria-label="Proposed changes">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-lg">Proposed changes</h3>
            {!draft.usedLlm && <span className="bg-accent px-2 text-[11px] font-bold uppercase leading-6 tracking-wider text-ink">Parsed with rules (model unavailable)</span>}
          </div>
          {draft.warnings.map((w, i) => (
            <Banner key={i} tone="info">
              {w}
            </Banner>
          ))}
          {changed.length === 0 ? (
            <p className="text-sm">No change from what you have now.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Each field, its current value and the proposed value</caption>
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-wider text-text">
                  <th scope="col" className="py-1">Field</th>
                  <th scope="col" className="py-1">Now</th>
                  <th scope="col" className="py-1" aria-hidden />
                  <th scope="col" className="py-1">Proposed</th>
                </tr>
              </thead>
              <tbody>
                {changed.map(([f, a, b]) => (
                  <tr key={f} className="border-b border-line/60">
                    <th scope="row" className="py-2 font-medium text-ink">{f}</th>
                    <td className="py-2 text-text line-through decoration-text/50">{a}</td>
                    <td className="py-2 text-primary" aria-label="changes to">→</td>
                    <td className="py-2 font-bold text-ink">{b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {draft.rejected.length > 0 && (
            <p className="text-xs text-text">
              Not used: {draft.rejected.join(" · ")}
            </p>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            <button type="button" onClick={() => onAccept(draft.values)} className="btn">
              Accept and review
            </button>
            <button type="button" onClick={() => onEdit(draft.values)} className="min-h-12 border border-ink px-5 font-medium text-ink">
              Edit
            </button>
            <button type="button" onClick={() => setDraft(null)} className="min-h-12 px-5 font-medium text-ink underline">
              Discard
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-line pt-3 text-sm">
        <p className="font-medium text-ink">What your agent can&apos;t do</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          <li>Save your rules on its own: only your Save button does.</li>
          <li>Give more than your budget: the platform refuses it.</li>
          <li>Give to causes you didn&apos;t pick.</li>
        </ul>
      </div>
    </section>
  );
}
