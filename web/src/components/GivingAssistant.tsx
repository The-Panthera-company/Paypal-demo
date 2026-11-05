"use client";

import { doodleTile, doodleUrl } from "@/lib/doodles";
import { Avatar } from "./Avatar";

const DEMO_DONOR = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1";
// WhatsApp-style doodle wallpaper behind the messages, in a faint teal on the mint surface
const WALLPAPER = doodleUrl(doodleTile({ stroke: "#b9d8cb", seed: 11 }));
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
  | { who: "me"; text: string }
  | { who: "bot"; text: string; chips: string[]; picks: Project[]; source: "ai" | "keywords" };

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
  useEffect(() => end.current?.scrollIntoView({ block: "nearest" }), [turns]);

  async function send(message: string) {
    if (!message.trim() || busy) return;
    setTurns((t) => [...t, { who: "me", text: message }]);
    setText("");
    setBusy(true);
    let answer: Extract<Turn, { who: "bot" }>;
    try {
      answer = AGENTS_URL ? await agentAnswer(message, projects) : keywordAnswer(message, projects);
    } catch {
      answer = keywordAnswer(message, projects);
    }
    setTurns((t) => [...t, answer]);
    setBusy(false);
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-24 right-4 z-30 flex min-h-12 items-center gap-2 bg-ink px-5 font-medium text-white shadow-lg hover:bg-primary lg:bottom-8 lg:right-8"
        >
          <Icon name="chat" size={20} className="text-cobalt-green" />
          Ask the giving assistant
        </button>
      )}

      {open && (
        <section
          aria-label="Giving assistant"
          className="fixed inset-x-0 bottom-0 z-40 flex max-h-[85vh] flex-col bg-white shadow-[0_15px_40px_rgba(0,0,0,0.2)] sm:inset-x-auto sm:bottom-8 sm:right-8 sm:w-[400px]"
        >
          <header className="flex items-center justify-between gap-3 bg-ink px-5 py-4 text-white">
            <div>
              <h2 className="text-lg text-white">Ask the giving assistant</h2>
              <p className="text-xs text-cobalt-green">{AGENTS_URL ? "AI · suggests, never pays" : "Keyword search · AI assistant coming soon"}</p>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="grid size-11 place-items-center" aria-label="Close assistant">
              <svg width="18" height="18" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M2 2l16 16M18 2L2 18" />
              </svg>
            </button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto bg-surface-alt p-4" style={{ backgroundImage: WALLPAPER, backgroundSize: "320px" }} aria-live="polite">
            {turns.length === 0 && (
              <div className="space-y-3">
                <p className="border border-line bg-white p-3 text-sm text-ink">
                  Tell me what you care about and I&apos;ll suggest verified projects. Try one of these:
                </p>
                {["Children learning to read, somewhere overlooked", "Clean water, urgently", "Trees and nature"].map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => send(q)}
                    className="block w-full border border-primary bg-white px-3 py-2 text-left text-sm text-primary hover:bg-primary-container"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            {turns.map((t, i) =>
              t.who === "me" ? (
                <div key={i} className="ml-auto flex w-fit max-w-[85%] items-end gap-2">
                  <p className="bg-primary px-3 py-2 text-sm text-white">{t.text}</p>
                  <Avatar seed={`donor-${DEMO_DONOR}`} anonymous size={28} label="You" />
                </div>
              ) : (
                <div key={i} className="space-y-2">
                  <div className="flex items-start gap-2">
                  <Avatar kind="assistant" seed="assistant" size={28} />
                  <div className="w-fit max-w-[85%] border border-line bg-white px-3 py-2 text-sm text-ink">
                    {t.chips.length > 0 && (
                      <>
                        <span>I searched for:</span>
                        <span className="my-1.5 flex flex-wrap gap-1.5">
                          {t.chips.map((c) => (
                            <span key={c} className="border border-primary px-2 text-xs leading-6 text-primary">
                              {c}
                            </span>
                          ))}
                        </span>
                      </>
                    )}
                    {t.text}
                  </div>
                  </div>
                  {t.picks.map((p) => (
                    <div key={p.id} className="flex items-center justify-between gap-3 border border-line bg-white px-3 py-2 text-sm">
                      <span>
                        <span className="block font-medium text-ink">{p.title}</span>
                        <span className="text-xs">
                          {p.backerCount} backers · {Math.round((p.raised.amount / p.goal.amount) * 100)}% funded
                        </span>
                      </span>
                      <Link href={`/projects/${p.id}#donate`} className="shrink-0 bg-ink px-3 py-2 text-xs font-bold uppercase tracking-wider text-white hover:bg-primary">
                        Back it
                      </Link>
                    </div>
                  ))}
                </div>
              ),
            )}
            {busy && <p className="text-sm">Looking…</p>}
            <div ref={end} />
          </div>

          <form
            className="flex shrink-0 border-t border-line bg-white"
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
              placeholder="Tell me what you care about…"
              className="min-h-12 min-w-0 flex-1 px-4 text-sm text-ink outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
            />
            <button className="shrink-0 bg-primary px-5 font-bold text-white focus-visible:-outline-offset-4 focus-visible:outline-white disabled:opacity-50" disabled={busy || !text.trim()}>
              Send
            </button>
          </form>
          <p className="shrink-0 bg-white px-4 py-2 text-[11px] leading-4">Suggestions come from verified projects only. Giving always goes through the normal PayPal checkout.</p>
        </section>
      )}
    </>
  );
}
