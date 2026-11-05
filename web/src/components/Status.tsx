"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

// One look for every system message on the site:
//   <Banner>   a message that stays on the page (errors in a form, sample-data notices)
//   notify()   a toast that comes and goes (saved, copied, payment done, couldn't connect)
//   <Confirm>  a modal that asks before anything that can't be undone
// plus an automatic "You're offline" banner.

export type Tone = "success" | "error" | "warning" | "info";

const toneStyle: Record<Tone, { bar: string; icon: string; label: string }> = {
  success: { bar: "border-growth", icon: "M5 12l4 4 10-10", label: "Done" },
  error: { bar: "border-cat-health", icon: "M12 8v5m0 3h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z", label: "Problem" },
  warning: { bar: "border-cat-education", icon: "M12 8v5m0 3h.01M12 3a9 9 0 100 18 9 9 0 000-18z", label: "Heads up" },
  info: { bar: "border-primary", icon: "M12 16v-5m0-3h.01M12 3a9 9 0 100 18 9 9 0 000-18z", label: "Note" },
};

function ToneIcon({ tone }: { tone: Tone }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0" aria-hidden>
      <path d={toneStyle[tone].icon} />
    </svg>
  );
}

/** A message that stays on the page. Errors are announced at once (role=alert), the rest politely. */
export function Banner({
  tone = "info",
  title,
  children,
  action,
  className = "",
}: {
  tone?: Tone;
  title?: string;
  children: React.ReactNode;
  action?: { label: string; onClick: () => void };
  className?: string;
}) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex gap-3 border-l-4 bg-white p-4 text-sm text-ink ${toneStyle[tone].bar} ${className}`}>
      <span className={tone === "error" ? "text-cat-health" : tone === "success" ? "text-growth" : tone === "warning" ? "text-cat-education" : "text-primary"}>
        <ToneIcon tone={tone} />
      </span>
      <div className="flex-1">
        {title && <p className="font-bold">{title}</p>}
        <div>{children}</div>
      </div>
      {action && (
        <button type="button" onClick={action.onClick} className="self-center whitespace-nowrap font-bold text-primary underline">
          {action.label}
        </button>
      )}
    </div>
  );
}

// ---- Toasts ----
type Toast = { id: number; tone: Tone; text: string };
const EVENT = "cg:notify";

/** Show a toast from anywhere (components, plain functions). */
export function notify(text: string, tone: Tone = "info") {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent<Omit<Toast, "id">>(EVENT, { detail: { text, tone } }));
}

const Ctx = createContext(notify);
/** Same as notify(), as a hook */
export const useNotify = () => useContext(Ctx);

export function StatusProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [offline, setOffline] = useState(false);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  useEffect(() => {
    const onNotify = (e: Event) => {
      const { text, tone } = (e as CustomEvent<Omit<Toast, "id">>).detail;
      const id = next.current++;
      // Same message twice in a row: keep one
      setToasts((t) => (t.some((x) => x.text === text) ? t : [...t.slice(-2), { id, text, tone }]));
      setTimeout(() => dismiss(id), tone === "error" ? 8000 : 4500);
    };
    const on = () => {
      setOffline(false);
      notify("You're back online.", "success");
    };
    const off = () => setOffline(true);
    setOffline(!navigator.onLine);
    window.addEventListener(EVENT, onNotify);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener(EVENT, onNotify);
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [dismiss]);

  return (
    <Ctx.Provider value={notify}>
      {children}
      {offline && (
        <div role="alert" className="fixed inset-x-0 top-0 z-[60] bg-cat-health px-4 py-2 text-center text-sm font-medium text-white">
          You&apos;re offline. Nothing will be charged; we&apos;ll reconnect when your internet is back.
        </div>
      )}
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col items-center gap-2 sm:inset-x-auto sm:left-1/2 sm:-translate-x-1/2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex w-full max-w-md animate-[toast-in_.25s_ease-out] items-start gap-3 border-l-[6px] p-4 bg-ink text-sm text-white shadow-[0_12px_30px_rgba(0,0,0,0.25)] sm:w-[420px] ${toneStyle[t.tone].bar}`}
          >
            <span className={t.tone === "success" ? "text-cobalt-green" : t.tone === "error" ? "text-white" : "text-accent"}>
              <ToneIcon tone={t.tone} />
            </span>
            <p className="flex-1">
              <span className="sr-only">{toneStyle[t.tone].label}: </span>
              {t.text}
            </p>
            <button type="button" onClick={() => dismiss(t.id)} className="-m-1 grid size-8 shrink-0 place-items-center text-white/70 hover:text-white" aria-label="Dismiss">
              ×
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

// ---- Confirm modal ----
/** Asks before anything that can't be undone. Native <dialog>: focus is trapped and Esc cancels. */
export function Confirm({
  open,
  title,
  body,
  confirmLabel = "Yes, continue",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="m-auto w-[min(92vw,460px)] whitespace-normal bg-white p-0 text-left leading-6 text-ink backdrop:bg-ink/60"
      aria-labelledby="confirm-title"
    >
      <div className="space-y-3 p-6">
        <h2 id="confirm-title" className="text-2xl">
          {title}
        </h2>
        <div className="text-text">{body}</div>
      </div>
      <div className="flex flex-wrap justify-end gap-3 border-t border-line bg-surface-alt p-4">
        <button type="button" onClick={onCancel} className="min-h-12 px-5 font-medium text-ink underline">
          {cancelLabel}
        </button>
        <button type="button" onClick={onConfirm} className={`min-h-12 px-5 font-bold text-white ${danger ? "bg-cat-health" : "bg-primary"}`} autoFocus>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
