"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Category, Project } from "@/lib/types";
import { DonatePanel } from "./DonatePanel";

// Giving to a whole category (design doc flow 1): before paying, the donor sees which projects the
// money may reach and how much, can exclude tags they object to, and pick how it's split.
// The numbers come from POST /donations/category-preview, the same rules the API uses at capture.

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
type Rule = "crowd" | "equal" | "closest_to_goal";
type Preview = { allocations: { id: string; title: string; cents: number }[]; excluded: { title: string; tag: string }[]; currency: string };

const RULES: { id: Rule; label: string; help: string }[] = [
  { id: "crowd", label: "Follow the crowd", help: "80% by how many people back each project, 20% shared equally" },
  { id: "equal", label: "Split equally", help: "Every open project gets the same share" },
  { id: "closest_to_goal", label: "Closest to goal", help: "Help the projects nearest to finishing" },
];

/** Same idea as the API's split, for sample-data mode only */
function samplePreview(projects: Project[], cents: number, rule: Rule, excluded: string[]): Preview {
  const out = projects.filter((p) => p.tags.some((t) => excluded.includes(t)));
  const open = projects.filter((p) => !out.includes(p));
  const weight = (p: Project) =>
    rule === "equal" ? 1 : rule === "closest_to_goal" ? p.raised.amount / p.goal.amount + 0.01 : Math.sqrt(p.backerCount) + 0.01;
  const total = open.reduce((s, p) => s + weight(p), 0) || 1;
  const allocations = open.map((p) => ({
    id: p.id,
    title: p.title,
    cents: Math.round(rule === "crowd" ? cents * 0.2 / open.length + (cents * 0.8 * weight(p)) / total : (cents * weight(p)) / total),
  }));
  return {
    allocations: allocations.sort((a, b) => b.cents - a.cents),
    excluded: out.map((p) => ({ title: p.title, tag: p.tags.find((t) => excluded.includes(t)) ?? "" })),
    currency: projects[0]?.goal.currency ?? "USD",
  };
}

export function CategoryCheckout({ category, projects }: { category: Category; projects: Project[] }) {
  const [rule, setRule] = useState<Rule>("crowd");
  const [excluded, setExcluded] = useState<string[]>([]);
  const [cents, setCents] = useState(1000);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tags = useMemo(() => [...new Set(projects.flatMap((p) => p.tags))].sort(), [projects]);
  const onAmount = useCallback((c: number) => setCents(c), []);

  useEffect(() => {
    if (!Number.isFinite(cents) || cents < 100) return;
    if (!API_URL || category.apiId === undefined) {
      setPreview(samplePreview(projects, cents, rule, excluded));
      return;
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      fetch(`${API_URL}/donations/category-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_id: category.apiId, amount_cents: cents, rule, excluded_tags: excluded }),
        signal: ctrl.signal,
      })
        .then(async (r) => {
          const d = await r.json();
          if (!r.ok) throw new Error(d?.detail?.message ?? "Preview unavailable");
          setError(null);
          setPreview({
            currency: d.currency,
            allocations: d.allocations.map((a: { project_id: number; title: string; amount_cents: number }) => ({ id: String(a.project_id), title: a.title, cents: a.amount_cents })),
            excluded: d.excluded.map((e: { title: string; matched_tag: string }) => ({ title: e.title, tag: e.matched_tag })),
          });
        })
        .catch((e) => e.name !== "AbortError" && setError(e.message));
    }, 300);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [cents, rule, excluded, category.apiId, projects]);

  const fmt = (c: number) =>
    new Intl.NumberFormat(undefined, { style: "currency", currency: preview?.currency ?? "USD", maximumFractionDigits: 2 }).format(c / 100);
  const nothingLeft = preview !== null && preview.allocations.length === 0;

  return (
    <div className="grid gap-10 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-8">
        <fieldset>
          <legend className="mb-3 text-xl font-display text-ink">1. How should it be split?</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {RULES.map((r) => (
              <label
                key={r.id}
                className={`flex cursor-pointer flex-col gap-1 border p-4 ${rule === r.id ? "border-primary bg-primary-container" : "border-line bg-white hover:border-primary"}`}
              >
                <span className="flex items-center gap-2 font-medium text-ink">
                  <input type="radio" name="rule" value={r.id} checked={rule === r.id} onChange={() => setRule(r.id)} className="accent-[#007190]" />
                  {r.label}
                </span>
                <span className="text-sm">{r.help}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-1 text-xl font-display text-ink">2. Anything you don&apos;t want to fund?</legend>
          <p className="mb-3 text-sm">Projects with a tag you exclude get nothing from this gift. The rule applies the same way for everyone.</p>
          <div className="flex flex-wrap gap-2">
            {tags.map((t) => {
              const on = excluded.includes(t);
              return (
                <button
                  key={t}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setExcluded((x) => (on ? x.filter((y) => y !== t) : [...x, t]))}
                  className={`min-h-11 border px-4 text-sm ${on ? "border-ink bg-ink text-white line-through" : "border-line bg-white text-ink hover:border-primary"}`}
                >
                  {on ? "Excluded: " : ""}
                  {t}
                </button>
              );
            })}
            {tags.length === 0 && <p className="text-sm">No tags in this category yet.</p>}
          </div>
        </fieldset>

        <section aria-live="polite">
          <h2 className="mb-3 text-xl text-ink">3. Where your {fmt(cents)} may go</h2>
          {error && <p role="alert" className="border-l-4 border-danger bg-white p-3 text-sm text-ink">{error}</p>}
          {nothingLeft ? (
            <p className="border border-dashed border-line bg-white p-6">
              Every project in {category.name} matches something you excluded. Remove an exclusion to continue.
            </p>
          ) : (
            <ul className="divide-y divide-line border border-line bg-white">
              {preview?.allocations.map((a) => (
                <li key={a.id} className="flex items-center gap-4 p-4">
                  <Link href={`/projects/${a.id}`} className="flex-1 font-medium text-ink hover:text-primary hover:underline">
                    {a.title}
                  </Link>
                  <span className="hidden h-2 w-32 bg-line sm:block" aria-hidden>
                    <span className="block h-2 bg-growth" style={{ width: `${Math.min(100, (a.cents / Math.max(1, cents)) * 100)}%` }} />
                  </span>
                  <span className="tabular w-20 text-right font-bold text-ink">{fmt(a.cents)}</span>
                </li>
              ))}
              {preview?.excluded.map((e) => (
                <li key={e.title} className="flex items-center gap-4 p-4 text-sm">
                  <span className="flex-1 line-through">{e.title}</span>
                  <span>excluded: {e.tag}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-sm">A preview: the final split is worked out when PayPal confirms the payment, using these same rules.</p>
        </section>
      </div>

      <aside className="h-fit space-y-4 border border-line bg-white p-6 lg:sticky lg:top-28">
        <h2 className="text-2xl">Give to all {category.name} projects</h2>
        <p className="text-sm">Your gift is shared out as shown. It also counts toward the matching pool for each project it reaches.</p>
        {nothingLeft ? (
          <p className="text-sm font-medium text-danger">Remove an exclusion to choose an amount.</p>
        ) : category.apiId !== undefined || !API_URL ? (
          <DonatePanel
            projectTitle={`${category.name} projects`}
            target={{ kind: "CATEGORY", categoryApiId: category.apiId ?? 0, rule, excludedTags: excluded }}
            onAmountChange={onAmount}
          />
        ) : null}
      </aside>
    </div>
  );
}
