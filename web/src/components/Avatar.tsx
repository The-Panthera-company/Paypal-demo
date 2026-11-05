// Avatars: initials in a 5x7 dot-matrix font (Nothing-style) over a faint doodle pattern of the
// platform's cause symbols (WhatsApp-wallpaper style). Pure SVG, no images, no network: the same
// name or id always draws the same avatar. Anonymous donors get a pattern-only avatar, no initials.

// 5x7 glyphs, one string per row ("1" = dot)
const GLYPHS: Record<string, string[]> = {
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  B: ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
  C: ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
  D: ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
  E: ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
  F: ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
  G: ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
  H: ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
  I: ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
  J: ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
  K: ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
  L: ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
  M: ["10001", "11011", "11111", "10101", "10001", "10001", "10001"],
  N: ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  P: ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
  Q: ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  S: ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  U: ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
  V: ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
  W: ["10001", "10001", "10001", "10101", "11111", "11011", "10001"],
  X: ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
  Y: ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
  Z: ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
  "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
  "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
  "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
};

// Background / dot colour pairs from the palette (all pass contrast for the dots)
const SCHEMES = [
  { bg: "#0b2e33", fg: "#96d1aa", doodle: "#1d4248" },
  { bg: "#007190", fg: "#ffefae", doodle: "#0a7f9e" },
  { bg: "#eef6f1", fg: "#0b2e33", doodle: "#d9e8df" },
  { bg: "#2f7d4f", fg: "#ffefae", doodle: "#3a8a5b" },
  { bg: "#7a5c2e", fg: "#ffefae", doodle: "#86683a" },
  { bg: "#b4533a", fg: "#ffffff", doodle: "#bf6049" },
];

import { DOODLES, rng } from "@/lib/doodles";

// Line-drawn characters for anonymous donors (100x100), in the style of the wallpaper's doodles
const CHARACTERS: { name: string; d: string; dots: [number, number][] }[] = [
  { name: "cat", d: "M31 42L28 21l16 11q6-2 12 0l16-11-3 21q8 12 0 25-9 11-19 11T31 67q-8-13 0-25zM47 58l3 3 3-3M20 57h15M21 64l14-2M80 57H65M79 64l-14-2", dots: [[41, 50], [59, 50]] },
  { name: "bear", d: "M50 30a24 24 0 110 48 24 24 0 010-48zM31 24a8 8 0 110 16 8 8 0 010-16zM69 24a8 8 0 110 16 8 8 0 010-16zM40 63q10-9 20 0-4 8-10 8t-10-8zM47 62h6", dots: [[42, 50], [58, 50]] },
  { name: "owl", d: "M30 32q20-14 40 0v32q-20 22-40 0zM41 36a8 8 0 110 16 8 8 0 010-16zM59 36a8 8 0 110 16 8 8 0 010-16zM47 55l3 5 3-5zM30 32l-2-8 8 5M70 32l2-8-8 5M40 70v8M60 70v8", dots: [[41, 44], [59, 44]] },
  { name: "robot", d: "M32 34h36v34H32zM50 34V24M50 18a3 3 0 110 6 3 3 0 010-6zM42 59h16M26 45v12M74 45v12M38 74v6M62 74v6", dots: [[42, 47], [58, 47]] },
  { name: "astronaut", d: "M50 22a28 28 0 110 56 28 28 0 010-56zM36 40h28a8 8 0 018 8v4a8 8 0 01-8 8H36a8 8 0 01-8-8v-4a8 8 0 018-8zM40 47q3-3 7-3M36 78l-4 6M64 78l4 6", dots: [] },
  { name: "monkey", d: "M50 30a22 22 0 110 44 22 22 0 010-44zM25 44a8 8 0 110 16 8 8 0 010-16zM75 44a8 8 0 110 16 8 8 0 010-16zM37 53q13-12 26 0 4 15-13 19-17-4-13-19zM45 63q5 4 10 0", dots: [[44, 50], [56, 50]] },
];

// Dotted speech bubble for the giving assistant (dot matrix, 9x7)
const BUBBLE = ["011111110", "111111111", "110101011", "111111111", "011111110", "000110000", "000100000"];

const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

export function initialsOf(name: string) {
  const parts = name.toUpperCase().replace(/[^A-Z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).replace(/[^A-Z0-9]/g, "");
}

function dotGrid(rows: string[], box: number) {
  const cols = rows[0].length;
  const cell = Math.min(box / cols, box / rows.length);
  const ox = (100 - cols * cell) / 2;
  const oy = (100 - rows.length * cell) / 2;
  const out: { x: number; y: number; r: number }[] = [];
  rows.forEach((row, r) => [...row].forEach((b, c) => b === "1" && out.push({ x: ox + (c + 0.5) * cell, y: oy + (r + 0.5) * cell, r: cell * 0.4 })));
  return out;
}

export function Avatar({
  name,
  seed,
  size = 48,
  anonymous = false,
  kind = "person",
  label,
}: {
  /** Display name: its initials are drawn */
  name?: string;
  /** Stable id for colour, pattern and character (defaults to the name) */
  seed?: string;
  size?: number;
  /** A doodle character instead of initials (privacy-first default for donors) */
  anonymous?: boolean;
  /** "assistant" draws a dotted speech bubble */
  kind?: "person" | "assistant";
  label?: string;
}) {
  const key = seed ?? name ?? "anon";
  const h = hash(key);
  const sc = SCHEMES[h % SCHEMES.length];
  const light = sc.bg === "#eef6f1";
  const text = anonymous || !name || kind === "assistant" ? "" : initialsOf(name);

  // Dense doodle wallpaper behind everything (4x4 small doodles, turned and sized by the seed)
  const r = rng(h);
  const wallpaper = Array.from({ length: 16 }, (_, i) => ({
    d: DOODLES[Math.floor(r() * DOODLES.length)],
    x: (i % 4) * 25 - 2 + r() * 6,
    y: Math.floor(i / 4) * 25 - 2 + r() * 6,
    rot: Math.round(r() * 60 - 30),
  }));

  let foreground: React.ReactNode;
  if (kind === "assistant") {
    foreground = <g fill={sc.fg}>{dotGrid(BUBBLE, 58).map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={p.r} />)}</g>;
  } else if (text) {
    // Initials: glyphs side by side with one blank column between
    const glyphs = text.split("").map((ch) => GLYPHS[ch]).filter(Boolean);
    const rows = Array.from({ length: 7 }, (_, row) => glyphs.map((g) => g[row]).join("0"));
    foreground = <g fill={sc.fg}>{dotGrid(rows, 62).map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={p.r} />)}</g>;
  } else {
    const ch = CHARACTERS[hash(`${key}:character`) % CHARACTERS.length];
    foreground = (
      <g>
        <path d={ch.d} fill={sc.bg} stroke={sc.fg} strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
        {ch.dots.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill={sc.fg} />)}
      </g>
    );
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label={label ?? (kind === "assistant" ? "Giving assistant" : text && name ? `${name}'s avatar` : "Anonymous donor")}
      className="shrink-0"
    >
      <rect width="100" height="100" fill={sc.bg} />
      <g fill="none" stroke={sc.doodle} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        {wallpaper.map((w, i) => <path key={i} d={w.d} transform={`translate(${w.x.toFixed(1)} ${w.y.toFixed(1)}) rotate(${w.rot} 12 12) scale(0.78)`} />)}
      </g>
      {foreground}
      {/* Light tiles get an edge so they don't melt into light pages */}
      {light && <rect x="1" y="1" width="98" height="98" fill="none" stroke="#9fb8ad" strokeWidth="2" />}
    </svg>
  );
}
