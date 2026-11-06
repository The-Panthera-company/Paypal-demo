"use client";

import Link from "next/link";
import { useActionState, useState, useTransition } from "react";
import { closeRoundAction, createRoundAction, updateRoundAction, type RoundFormState } from "@/app/admin/actions";
import { Banner, Confirm, notify } from "@/components/Status";
import type { RoundInfo } from "@/lib/admin";

const field = "min-h-11 w-full border border-line bg-white px-3 text-sm text-ink";
const local = (iso: string) => {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const STATUS: Record<RoundInfo["status"], string> = { scheduled: "bg-accent text-ink", open: "bg-growth text-white", closing: "bg-cat-education text-white", closed: "bg-line text-ink" };

function RoundForm({ round, action, submit }: { round?: RoundInfo; action: (s: RoundFormState, f: FormData) => Promise<RoundFormState>; submit: string }) {
  const [state, formAction, pending] = useActionState(action, null);
  const open = round?.status === "open";
  return (
    <form action={formAction} className="grid gap-3 sm:grid-cols-2">
      {round && <input type="hidden" name="id" value={round.id} />}
      {round && <input type="hidden" name="status" value={round.status} />}
      <label className="text-sm text-ink sm:col-span-2">
        Name
        <input name="name" required={!round} defaultValue={round?.name} className={field} placeholder="December round" />
      </label>
      <label className="text-sm text-ink">
        Starts
        <input name="starts_at" type="datetime-local" required={!round} disabled={open} defaultValue={round ? local(round.startsAt) : undefined} className={`${field} disabled:opacity-60`} />
        {open && <span className="text-xs text-text">An open round&apos;s start can&apos;t change.</span>}
      </label>
      <label className="text-sm text-ink">
        Ends
        <input name="ends_at" type="datetime-local" required={!round} defaultValue={round ? local(round.endsAt) : undefined} className={field} />
      </label>
      <label className="text-sm text-ink">
        Matching pool ($)
        <input name="pool" type="number" min="0" step="1" required={!round} defaultValue={round ? round.pool / 100 : undefined} className={field} />
      </label>
      <label className="text-sm text-ink">
        Per-person cap per project ($)
        <input name="per_person_cap" type="number" min="1" step="1" defaultValue={round ? round.perPersonCap / 100 : 50} className={field} />
      </label>
      <label className="text-sm text-ink">
        Project cap (% of category pool)
        <input name="project_cap_pct" type="number" min="1" max="100" step="1" defaultValue={round?.projectCapPct ?? 30} className={field} />
      </label>
      <label className="text-sm text-ink">
        Floor (% shared equally)
        <input name="floor_pct" type="number" min="0" max="100" step="1" defaultValue={round?.floorPct ?? 20} className={field} />
      </label>
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <button className="btn btn-2 disabled:opacity-50" disabled={pending}>
          {pending ? "Saving…" : submit}
        </button>
      </div>
      {state && (
        <div className="sm:col-span-2">
          <Banner tone={state.ok ? "success" : "error"}>{state.message}</Banner>
        </div>
      )}
    </form>
  );
}

export function RoundsPanel({ rounds }: { rounds: RoundInfo[] }) {
  const current = rounds.find((r) => r.status === "open" || r.status === "closing") ?? rounds.find((r) => r.status === "scheduled");
  const [asking, setAsking] = useState(false);
  const [pending, start] = useTransition();
  const [closeMsg, setCloseMsg] = useState<{ ok: boolean; message: string } | null>(null);
  const fmt = (r: RoundInfo) => new Intl.NumberFormat(undefined, { style: "currency", currency: r.currency, maximumFractionDigits: 0 }).format(r.pool / 100);
  const day = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="space-y-6">
      <section className="bg-white p-6">
        <h2 className="text-2xl">Rounds</h2>
        {rounds.length === 0 ? (
          <p className="mt-2 text-sm">No rounds yet.</p>
        ) : (
          <table className="mt-4 w-full text-left text-sm">
            <thead className="border-b border-line">
              <tr>
                <th className="py-2 font-medium">Round</th>
                <th className="py-2 font-medium">When</th>
                <th className="py-2 text-right font-medium">Pool</th>
                <th className="py-2 font-medium">Status</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {rounds.map((r) => (
                <tr key={r.id} className="border-b border-line last:border-0">
                  <td className="py-3 font-medium text-ink">{r.name}</td>
                  <td className="py-3">
                    {day(r.startsAt)} → {day(r.endsAt)}
                  </td>
                  <td className="tabular py-3 text-right text-ink">{fmt(r)}</td>
                  <td className="py-3">
                    <span className={`px-2 text-[11px] font-bold uppercase leading-6 tracking-wider ${STATUS[r.status]}`}>{r.status}</span>
                  </td>
                  <td className="py-3 text-right">
                    <Link href={`/rounds/${r.id}`} className="font-medium text-primary underline">
                      Results
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {current && current.status !== "closing" && (
        <section className="space-y-4 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-2xl">Edit {current.status === "open" ? "the open round" : "the scheduled round"}: {current.name}</h2>
            {current.status === "open" && (
              <button type="button" onClick={() => setAsking(true)} disabled={pending} className="min-h-11 bg-cat-health px-5 text-sm font-bold text-white disabled:opacity-50">
                {pending ? "Closing…" : "Close round now"}
              </button>
            )}
          </div>
          {closeMsg && <Banner tone={closeMsg.ok ? "success" : "error"}>{closeMsg.message}</Banner>}
          <RoundForm key={current.id} round={current} action={updateRoundAction} submit="Save changes" />
          <Confirm
            open={asking}
            title={`Close ${current.name} now?`}
            body={
              <>
                Final matching is calculated and added to each project&apos;s next milestone. This can&apos;t be undone. If a Watchdog case is open, the round waits for it.
              </>
            }
            confirmLabel="Close round"
            danger
            onCancel={() => setAsking(false)}
            onConfirm={() => {
              setAsking(false);
              start(async () => {
                const r = await closeRoundAction(current.id);
                setCloseMsg(r);
                notify(r.message, r.ok ? "success" : "error");
              });
            }}
          />
        </section>
      )}

      <section className="space-y-4 bg-white p-6">
        <h2 className="text-2xl">Schedule a round</h2>
        <p className="text-sm">One round at a time: a new one can&apos;t overlap the current one. It opens by itself at its start time.</p>
        <RoundForm action={createRoundAction} submit="Schedule round" />
      </section>
    </div>
  );
}
