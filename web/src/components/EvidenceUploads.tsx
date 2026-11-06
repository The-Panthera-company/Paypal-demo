"use client";

import { useEffect, useState } from "react";
import { loadOwner, saveOwner } from "@/lib/owner-tokens";
import { Banner, notify } from "./Status";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const field = "min-h-11 border border-line bg-white px-3 text-sm text-ink";
type M = { id: number; seq?: number; title: string; amount_cents: number; status: string; due_date?: string | null };
const STATUS: Record<string, string> = { open: "Waiting for evidence", evidence_submitted: "Evidence being checked", held: "Held for an admin", released: "Released" };
const MESSAGES: Record<string, string> = {
  BAD_PROJECT_TOKEN: "That project token isn't right. Check it, or ask an admin for a new one.",
  MILESTONE_NOT_OPEN: "This step isn't taking evidence (it's held or already released).",
};

async function post(projectId: string, token: string, body: Record<string, unknown>) {
  const r = await fetch(`${API_URL}/projects/${projectId}/documents`, { method: "POST", headers: { "Content-Type": "application/json", "X-Project-Token": token }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const code = d?.detail?.error as string | undefined;
    if (r.status === 422 && !code) throw new Error("Use a full https:// link (http:// links aren't accepted).");
    throw new Error((code && MESSAGES[code]) || d?.detail?.message || `Upload failed (${r.status}).`);
  }
  return d;
}

function LinkForm({ label, kinds, onSend }: { label: string; kinds: string[]; onSend: (kind: string, url: string) => Promise<void> }) {
  const [kind, setKind] = useState(kinds[0]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = /^https:\/\/\S+\.\S+/.test(url.trim());
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onSend(kind, url.trim());
          setUrl("");
        } finally {
          setBusy(false);
        }
      }}
    >
      <label className="flex flex-col text-sm text-ink">
        Type
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k[0].toUpperCase() + k.slice(1)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-[240px] flex-1 flex-col text-sm text-ink">
        {label}
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://drive.google.com/…" className={field} aria-invalid={Boolean(url) && !ok} />
      </label>
      <button className="btn btn-2 !min-h-11 disabled:opacity-50" disabled={!ok || busy}>
        {busy ? "Sending…" : "Add"}
      </button>
    </form>
  );
}

// Evidence uploads for a project owner: token (saved from the application), each milestone's
// status, and a link form on every open step. The API stores https links, not files.
export function EvidenceUploads({ projectId, listed }: { projectId: string; listed: { title: string; milestones: M[] } | null }) {
  const [token, setToken] = useState("");
  const [title, setTitle] = useState(listed?.title ?? `Project ${projectId}`);
  const [milestones, setMilestones] = useState<M[]>(listed?.milestones ?? []);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    const saved = loadOwner(projectId);
    if (saved) {
      setToken(saved.token);
      if (!listed) {
        setTitle(saved.title);
        setMilestones(saved.milestones.map((m) => ({ ...m, status: "open" })));
      }
    }
  }, [projectId, listed]);

  const send = async (body: Record<string, unknown>, after?: () => void) => {
    setMsg(null);
    try {
      await post(projectId, token.trim(), body);
      const saved = loadOwner(projectId);
      if (saved && saved.token !== token.trim()) saveOwner(projectId, { ...saved, token: token.trim() });
      after?.();
      const text = body.milestone_id ? "Evidence added. That step is now being checked." : "Document added.";
      setMsg({ ok: true, text });
      notify(text, "success");
    } catch (e) {
      const text = e instanceof Error ? e.message : "Upload failed.";
      setMsg({ ok: false, text });
      notify(text, "error");
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="space-y-3 bg-white p-6">
        <h2 className="text-2xl">{title}</h2>
        {!listed && <Banner tone="info">This project isn&apos;t public yet: it&apos;s waiting for an admin to verify it. You can still add documents.</Banner>}
        <label className="block text-sm text-ink">
          Project token
          <input value={token} onChange={(e) => setToken(e.target.value)} className={`${field} w-full font-mono`} placeholder="Paste the token you got when you applied" autoComplete="off" />
        </label>
        <p className="text-xs">Saved in this browser if you applied here. Lost it? An admin can issue a new one.</p>
        <Banner tone="info">We store links, not files: upload to Google Drive (share as “anyone with the link”) or Imgur, then paste the https:// link.</Banner>
      </section>

      {msg && <Banner tone={msg.ok ? "success" : "error"}>{msg.text}</Banner>}

      <section className="space-y-4 bg-white p-6">
        <h2 className="text-xl">Milestones</h2>
        {milestones.length === 0 ? (
          <p className="text-sm">No milestones found for this project.</p>
        ) : (
          <ol className="space-y-4">
            {milestones.map((m, i) => (
              <li key={m.id} className="space-y-3 border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-ink">
                    {m.seq ?? i + 1}. {m.title} · {new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(m.amount_cents / 100)}
                  </p>
                  <span className={`px-2 text-[11px] font-bold uppercase leading-6 tracking-wider ${m.status === "released" ? "bg-cobalt-green text-ink" : m.status === "open" ? "bg-accent text-ink" : "bg-line text-ink"}`}>
                    {STATUS[m.status] ?? m.status}
                  </span>
                </div>
                {m.status === "open" && (
                  <LinkForm
                    label="Receipt or photo link"
                    kinds={["receipt", "photo"]}
                    onSend={(kind, url) => send({ kind, file_url: url, milestone_id: m.id }, () => setMilestones((all) => all.map((x) => (x.id === m.id ? { ...x, status: "evidence_submitted" } : x))))}
                  />
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="space-y-3 bg-white p-6">
        <h2 className="text-xl">Registration and plan</h2>
        <p className="text-sm">Help the admin verify you: your registration certificate and project plan.</p>
        <LinkForm label="Document link" kinds={["registration", "plan"]} onSend={(kind, url) => send({ kind, file_url: url })} />
      </section>
    </div>
  );
}
