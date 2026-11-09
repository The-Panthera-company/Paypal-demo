"use client";

import { useState, useTransition } from "react";
import { verifyChainAction } from "@/app/admin/actions";
import type { ChainCheck, ChainRow } from "@/lib/admin";

const short = (h: string | null) => (h ? h.slice(0, 10) : "—");

// The audit hash chain: each row stores the previous row's hash, so editing any row breaks every link after it.
export function TrustPanel({ initial, rows: initialRows }: { initial: ChainCheck | null; rows: ChainRow[] }) {
  const [check, setCheck] = useState(initial);
  const [rows, setRows] = useState(initialRows);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const verify = () =>
    start(async () => {
      const r = await verifyChainAction();
      if (r.ok) {
        setCheck(r.check);
        setRows(r.rows);
        setError(null);
      } else setError(r.message);
    });

  return (
    <div className="space-y-5">
      <p className="max-w-[70ch]">
        Each row includes the previous row&apos;s hash. Editing any row breaks the chain, and the check below names the first row that no longer matches.
      </p>
      <div className="flex flex-wrap items-center gap-4 bg-white p-5">
        <div role="status" aria-live="polite" className="min-w-0 flex-1">
          {check === null ? (
            <p className="font-bold text-ink">Not checked yet</p>
          ) : check.valid ? (
            <p className="inline-flex items-center gap-2 bg-cobalt-green px-3 py-1 font-bold text-ink">
              <span aria-hidden>✓</span> Verified · {check.checked.toLocaleString()} entries
            </p>
          ) : (
            <p className="inline-flex items-center gap-2 bg-cat-health px-3 py-1 font-bold text-white">
              <span aria-hidden>✕</span> Broken at #{check.firstBadId}
            </p>
          )}
          {check && !check.valid && check.firstBadReason && <p className="mt-2 text-sm">{check.firstBadReason}</p>}
          {check?.headHash && <p className="mt-2 text-xs text-text">Latest hash <code className="text-primary">{short(check.headHash)}…</code></p>}
          {error && <p className="mt-2 text-sm text-cat-health">{error}</p>}
        </div>
        <button type="button" onClick={verify} disabled={pending} className="btn btn-2 disabled:opacity-50">
          {pending ? "Checking…" : "Verify now"}
        </button>
      </div>

      <div className="overflow-x-auto bg-white">
        <table className="w-full min-w-[640px] text-left text-sm">
          <caption className="sr-only">The latest audit entries with their hash links</caption>
          <thead className="bg-ink text-white">
            <tr>
              {["Seq", "Actor", "Action", "Rule", "Hash", "Previous hash"].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-4">No audit entries yet.</td>
              </tr>
            ) : (
              rows.map((r) => {
                const bad = check && !check.valid && r.id === check.firstBadId;
                return (
                  <tr key={r.id} className={`border-t border-line ${bad ? "bg-cat-health/10" : ""}`}>
                    <td className="tabular px-3 py-2">{r.seq ?? r.id}</td>
                    <td className="px-3 py-2">{r.actor}</td>
                    <td className="px-3 py-2">{r.action.replaceAll("_", " ")}</td>
                    <td className="px-3 py-2">{r.rule ?? "—"}</td>
                    <td className="px-3 py-2"><code className="text-primary">{short(r.hash)}</code></td>
                    <td className="px-3 py-2"><code className="text-text">{short(r.prevHash)}</code></td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
