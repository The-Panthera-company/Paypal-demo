"use client";

import { useState, useTransition } from "react";
import { newOwnerTokenAction } from "@/app/admin/actions";
import { Confirm, notify } from "@/components/Status";

// Issue a new X-Project-Token (seeded projects, lost tokens). The old one stops working.
export function OwnerTokenButton({ projectId, withInput = false }: { projectId?: string; withInput?: boolean }) {
  const [id, setId] = useState(projectId ?? "");
  const [token, setToken] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [pending, start] = useTransition();
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        {withInput && (
          <label className="flex flex-col text-sm text-ink">
            Project id
            <input value={id} onChange={(e) => setId(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="min-h-10 w-32 border border-line px-3 text-sm" />
          </label>
        )}
        <button type="button" disabled={!id || pending} onClick={() => setAsking(true)} className="min-h-10 border border-line bg-white px-3 text-xs font-bold uppercase tracking-wider text-ink hover:border-primary disabled:opacity-50">
          {pending ? "…" : "New owner token"}
        </button>
      </div>
      {token && (
        <p className="text-sm">
          New token for project {id} (shown once; send it to the owner):{" "}
          <code className="break-all bg-surface-alt px-2 py-1 text-ink">{token}</code>
        </p>
      )}
      <Confirm
        open={asking}
        title={`New owner token for project ${id}?`}
        body="The project's current token stops working. The new one is shown once."
        confirmLabel="Issue new token"
        onCancel={() => setAsking(false)}
        onConfirm={() => {
          setAsking(false);
          start(async () => {
            const r = await newOwnerTokenAction(id);
            if (r.ok) setToken(r.token);
            notify(r.ok ? "New owner token issued." : r.message, r.ok ? "success" : "error");
          });
        }}
      />
    </div>
  );
}
