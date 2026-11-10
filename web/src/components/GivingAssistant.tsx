"use client";

import { BundiIcon } from "./BundiIcon";
import { doodleTile, doodleUrl } from "@/lib/doodles";
import { Avatar } from "./Avatar";

// WhatsApp-style doodle wallpaper (with little avatar faces) behind the messages, faint teal on mint
const WALLPAPER = doodleUrl(doodleTile({ stroke: "#b9d8cb", seed: 11, density: 7 }));
const clock = () => new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Project } from "@/lib/types";
import { Icon } from "./Icon";

// Discovery chat (design doc: "chat-lite"). With NEXT_PUBLIC_AGENTS_URL set it asks Person 3's
// Discovery agent (POST /agents/discovery/chat → { filters, projects, explanation }). Without it,
// it falls back to a keyword search over the listed projects and says so. Either way it only
// suggests: giving always goes through the project page and PayPal.

const AGENTS_URL = process.env.NEXT_PUBLIC_AGENTS_URL?.replace(/\/$/, "");

type Turn =
  | { who: "me"; text: string; at?: string }
  | { who: "bot"; text: string; chips: string[]; picks: Project[]; source: "ai" | "keywords"; at?: string };

const SYNONYMS: [RegExp, (p: Project) => boolean, string][] = [
  [/\b(read|reading|book|books|library|literacy)\b/i, (p) => /book|librar|literacy|read/i.test(p.title + p.summary + p.facets.cause + p.tags.join(" ")), "Books & reading"],
  [/\b(school|class|classroom|desk|learn|education|stem|study)\b/i, (p) => p.categoryId === "education", "Education"],
  [/\b(health|clinic|doctor|medicine|medical|sick|disease|eye|lupus)\b/i, (p) => p.categoryId === "health", "Health"],
  [/\b(water|well|borehole|pump|drink)\b/i, (p) => p.categoryId === "water", "Water"],
  [/\b(tree|trees|forest|environment|climate|nature|lake|plant)\b/i, (p) => p.categoryId === "environment", "Environment"],
  [/\b(child|children|kid|kids|pupil|pupils|girl|girls)\b/i, (p) => /child|youth/i.test(p.facets.group), "Children & youth"],
  [/\b(elderly|old|older|grandparent)\b/i, (p) => /elder/i.test(p.facets.group), "Elderly"],
  [/\b(adult|adults|women|men|patient|patients)\b/i, (p) => /adult/i.test(p.facets.group), "Adults"],
];

function keywordAnswer(message: string, projects: Project[]): Extract<Turn, { who: "bot" }> {
  const hits = SYNONYMS.filter(([re]) => re.test(message));
  const regions = [...new Set(projects.map((p) => p.facets.region))].filter((r) => message.toLowerCase().includes(r.toLowerCase()));
  let list = projects.filter((p) => hits.every(([, test]) => test(p)) && (regions.length === 0 || regions.includes(p.facets.region)));
  const chips = [...hits.map(([, , chip]) => chip), ...regions];
  const overlooked = /\b(overlooked|ignored|forgotten|few backers|nobody|small)\b/i.test(message);
  const urgent = /\b(urgent|urgently|now|emergency|soon)\b/i.test(message);
  if (overlooked) chips.push("Few backers");
  if (urgent) chips.push("Most urgent");
  list = [...list].sort((a, b) => (overlooked ? a.backerCount - b.backerCount : 0) || (urgent ? b.urgency - a.urgency : 0) || b.urgency - a.urgency);
  const picks = list.slice(0, 3);
  let text: string;
  if (chips.length === 0) text = "Tell me a cause (health, education, water, trees), who you'd like to help, or a region, and I'll find matching projects.";
  else if (picks.length === 0) text = "No listed project matches all of that. Try fewer words, or browse all projects.";
  else {
    const first = picks[0];
    text =
      `${picks.length === 1 ? "One project fits" : `${picks.length} projects fit`}.` +
      (first.backerCount < 5 ? ` ${first.title} has only ${first.backerCount} backer${first.backerCount === 1 ? "" : "s"}, so your gift counts extra in matching.` : "");
  }
  return { who: "bot", text, chips, picks, source: "keywords" };
}

async function agentAnswer(message: string, projects: Project[]): Promise<Extract<Turn, { who: "bot" }>> {
  const res = await fetch(`${AGENTS_URL}/agents/discovery/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(String(res.status));
  const data = (await res.json()) as { filters?: Record<string, string>; projects?: { id: string | number }[]; explanation?: string };
  const ids = (data.projects ?? []).map((p) => String(p.id));
  return {
    who: "bot",
    text: data.explanation ?? "Here's what I found.",
    chips: Object.values(data.filters ?? {}),
    picks: projects.filter((p) => ids.includes(p.id)).slice(0, 3),
    source: "ai",
  };
}

export function GivingAssistant({ projects }: { projects: Project[] }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  // Braces matter: newer browsers make scrollIntoView return a Promise, and an effect that returns
  // anything but a cleanup function crashes React on the next update ("destroy is not a function")
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [turns]);

  async function send(message: string) {
    if (!message.trim() || busy) return;
    setTurns((t) => [...t, { who: "me", text: message, at: clock() }]);
    setText("");
    setBusy(true);
    let answer: Extract<Turn, { who: "bot" }>;
    try {
      answer = AGENTS_URL ? await agentAnswer(message, projects) : keywordAnswer(message, projects);
    } catch {
      answer = keywordAnswer(message, projects);
    }
    setTurns((t) => [...t, { ...answer, at: clock() }]);
    setBusy(false);
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Ask Bundi, the giving assistant"
          className="fixed bottom-24 right-4 z-30 flex min-h-12 min-w-12 items-center justify-center gap-2 bg-ink px-3 font-medium sm:px-5 text-white shadow-lg hover:bg-primary lg:bottom-8 lg:right-8"
        >
          <span className="grid size-9 place-items-center bg-[#fffaf2] text-[#6b4a3a]"><BundiIcon size={30} /></span>
          <span className="max-sm:hidden">Ask Bundi</span>
        </button>
      )}

      {open && (
        <section
          aria-label="Giving assistant"
          className="fixed inset-x-0 bottom-0 z-40 flex h-[85vh] max-h-[680px] flex-col overflow-hidden bg-white shadow-[0_15px_40px_rgba(0,0,0,0.25)] sm:inset-x-auto sm:bottom-8 sm:right-8 sm:w-[400px]"
        >
          {/* Chat header, messaging-app style */}
          <header className="flex shrink-0 items-center gap-3 bg-ink px-4 py-3 text-white">
            <span className="relative">
              <Avatar kind="assistant" seed="assistant" size={40} />
              <span className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full bg-cobalt-green ring-2 ring-ink" aria-hidden />
            </span>
            <div className="flex-1">
              <h2 className="text-lg leading-6 text-white">Giving assistant</h2>
              <p className="text-xs text-cobalt-green">{busy ? "typing…" : AGENTS_URL ? "online · suggests, never pays" : "online · keyword search"}</p>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="grid size-11 place-items-center" aria-label="Close assistant">
              <svg width="18" height="18" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M2 2l16 16M18 2L2 18" />
              </svg>
            </button>
          </header>

          {/* Conversation on the doodle wallpaper */}
          <div className="flex-1 space-y-2 overflow-y-auto bg-[#e7f1ec] px-3 py-4" style={{ backgroundImage: WALLPAPER, backgroundSize: "300px" }} aria-live="polite">
            {/* The disclaimer, set apart like a messaging app's system notice */}
            <p className="sticky top-0 z-10 mx-auto mb-3 max-w-[300px] rounded-lg border border-[#e8d98a] bg-accent px-3 py-2 text-center text-[11px] leading-4 text-ink shadow-sm">
              <span aria-hidden>🔒 </span>Suggestions come from verified projects only. Giving always goes through the normal PayPal checkout.
            </p>

            {turns.length === 0 && (
              <div className="space-y-2">
                <div className="flex items-end gap-2">
                  <Avatar kind="assistant" seed="assistant" size={28} />
                  <p className="relative max-w-[80%] rounded-lg rounded-bl-none bg-white px-3 py-2 text-sm text-ink shadow-sm">
                    Hi! Tell me what you care about and I&apos;ll suggest verified projects. Try one of these:
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 pl-9">
                  {["Children learning to read, somewhere overlooked", "Clean water, urgently", "Trees and nature"].map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => send(q)}
                      className="rounded-full border border-primary bg-white px-3 py-1.5 text-left text-xs text-primary shadow-sm hover:bg-primary hover:text-white"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((t, i) =>
              t.who === "me" ? (
                <div key={i} className="flex justify-end">
                  <p className="relative max-w-[80%] rounded-lg rounded-br-none bg-cobalt-green px-3 pb-1.5 pt-2 text-sm text-ink shadow-sm">
                    {t.text}
                    <span className="mt-0.5 block text-right text-[10px] text-ink/60">
                      {t.at} <span aria-label="sent">✓✓</span>
                    </span>
                  </p>
                </div>
              ) : (
                <div key={i} className="space-y-2">
                  <div className="flex items-end gap-2">
                    <Avatar kind="assistant" seed="assistant" size={28} />
                    <div className="relative max-w-[80%] rounded-lg rounded-bl-none bg-white px-3 pb-1.5 pt-2 text-sm text-ink shadow-sm">
                      {t.chips.length > 0 && (
                        <span className="mb-1.5 flex flex-wrap gap-1.5">
                          {t.chips.map((c) => (
                            <span key={c} className="rounded-full bg-primary-container px-2 text-xs leading-6 text-primary">
                              {c}
                            </span>
                          ))}
                        </span>
                      )}
                      {t.text}
                      <span className="mt-0.5 block text-right text-[10px] text-text">{t.at}</span>
                    </div>
                  </div>
                  {t.picks.length > 0 && (
                    <div className="ml-9 max-w-[80%] overflow-hidden rounded-lg bg-white shadow-sm">
                      {t.picks.map((p) => (
                        <div key={p.id} className="flex items-center justify-between gap-3 border-b border-line px-3 py-2 text-sm last:border-0">
                          <span>
                            <span className="block font-medium text-ink">{p.title}</span>
                            <span className="text-xs">
                              {p.backerCount} backers · {Math.round((p.raised.amount / p.goal.amount) * 100)}% funded
                            </span>
                          </span>
                          <Link href={`/projects/${p.id}#donate-box`} className="shrink-0 rounded-full bg-ink px-3 py-1.5 text-xs font-bold text-white hover:bg-primary">
                            Back it
                          </Link>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ),
            )}
            {busy && (
              <div className="flex items-end gap-2">
                <Avatar kind="assistant" seed="assistant" size={28} />
                <p className="rounded-lg rounded-bl-none bg-white px-4 py-3 shadow-sm" aria-label="The assistant is typing">
                  <span className="inline-flex gap-1" aria-hidden>
                    {[0, 1, 2].map((d) => (
                      <span key={d} className="size-1.5 animate-bounce rounded-full bg-text" style={{ animationDelay: `${d * 150}ms` }} />
                    ))}
                  </span>
                </p>
              </div>
            )}
            <div ref={end} />
          </div>

          {/* Input bar, its own strip */}
          <form
            className="flex shrink-0 items-center gap-2 border-t border-line bg-surface px-3 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              send(text);
            }}
          >
            <label htmlFor="assistant-input" className="sr-only">
              What do you care about?
            </label>
            <input
              id="assistant-input"
              ref={input}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type a message"
              className="min-h-11 min-w-0 flex-1 rounded-full border border-line bg-white px-4 text-sm text-ink outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
            />
            <button
              className="grid size-11 shrink-0 place-items-center rounded-full bg-primary text-white hover:bg-ink focus-visible:outline-offset-2 disabled:opacity-40"
              disabled={busy || !text.trim()}
              aria-label="Send"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M3 20l18-8L3 4v6l12 2-12 2z" />
              </svg>
            </button>
          </form>
        </section>
      )}
    </>
  );
}
