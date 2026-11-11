"use client";

import { useEffect, useState, useTransition } from "react";
import { getPayoutEmailAction, setPayoutEmailAction } from "@/app/admin/actions";
import { notify } from "@/components/Status";

// PayPal email a project's tranches are paid to (in the sandbox: a sandbox personal account).
export function PayoutEmailField({ projectId: fixed, withInput = false }: { projectId?: string; withInput?: boolean }) {
  const [projectId, setProjectId] = useState(fixed ?? "");
  const [email, setEmail] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [pending, start] = useTransition();
  useEffect(() => {
    if (!projectId) return;
    setLoaded(false);
    getPayoutEmailAction(projectId).then((r) => {
      if (r.ok) setEmail(r.email ?? "");
      setLoaded(true);
    });
  }, [projectId]);
  const ok = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await setPayoutEmailAction(projectId, email);
          notify(r.message, r.ok ? "success" : "error");
        });
      }}
    >
      {withInput && (
        <label className="flex flex-col text-sm text-ink">
          Project id
          <input value={projectId} onChange={(e) => setProjectId(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="min-h-10 w-28 border border-line px-3 text-sm" />
        </label>
      )}
      <label className="flex flex-col text-sm text-ink">
        PayPal email for payouts
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!loaded} placeholder={loaded ? "sandbox-personal@example.com" : "Loading…"} className="min-h-10 w-72 border border-line px-3 text-sm" />
      </label>
      <button disabled={!ok || !projectId || pending} className="min-h-10 border border-line bg-white px-3 text-xs font-bold uppercase tracking-wider text-ink hover:border-primary disabled:opacity-50">
        {pending ? "Saving…" : "Save"}
      </button>
    </form>
  );
}
