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
  M: ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
  N: ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  P: ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
  Q: ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  S: ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  U: ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
  V: ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
  W: ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
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

// Tiny cause doodles in a 24x24 box: water drop, leaf, heart, book
const DOODLES = [
  "M12 4c3 4 5 6.5 5 9a5 5 0 01-10 0c0-2.5 2-5 5-9z",
  "M6 18C6 10 11 6 18 6c0 7-4 12-12 12zm0 0l6-6",
  "M12 19s-7-4.3-7-9a4 4 0 017-2.6A4 4 0 0119 10c0 4.7-7 9-7 9z",
  "M5 6h6a2 2 0 012 2v10a2 2 0 00-2-2H5zm14 0h-6a2 2 0 00-2 2v10a2 2 0 012-2h6z",
];

const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

export function initialsOf(name: string) {
  const parts = name.toUpperCase().replace(/[^A-Z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).replace(/[^A-Z0-9]/g, "");
}

export function Avatar({
  name,
  seed,
  size = 48,
  anonymous = false,
  label,
}: {
  /** Display name: its initials are drawn */
  name?: string;
  /** Stable id for colour and pattern (defaults to the name) */
  seed?: string;
  size?: number;
  /** Pattern only, no initials (privacy-first default for donors) */
  anonymous?: boolean;
  label?: string;
}) {
  const key = seed ?? name ?? "anon";
  const h = hash(key);
  const sc = SCHEMES[h % SCHEMES.length];
  const text = anonymous || !name ? "" : initialsOf(name);
  const glyphs = text.split("").map((ch) => GLYPHS[ch]).filter(Boolean);

  // Dot matrix: each glyph 5 columns + 1 gap, 7 rows; fitted into the middle 60% of the tile
  const cols = glyphs.length * 6 - 1;
  const cell = glyphs.length ? Math.min(60 / cols, 60 / 7) : 0;
  const ox = (100 - cols * cell) / 2;
  const oy = (100 - 7 * cell) / 2;
  const dots: { x: number; y: number }[] = [];
  glyphs.forEach((g, gi) =>
    g.forEach((row, r) =>
      [...row].forEach((bit, c) => {
        if (bit === "1") dots.push({ x: ox + (gi * 6 + c + 0.5) * cell, y: oy + (r + 0.5) * cell });
      }),
    ),
  );

  // Doodle wallpaper: a 3x3 grid of small symbols, rotated and picked by the seed
  const doodles = Array.from({ length: 9 }, (_, i) => {
    const v = hash(key + i);
    return { d: DOODLES[v % DOODLES.length], x: (i % 3) * 36 - 4 + (v % 7), y: Math.floor(i / 3) * 36 - 4 + ((v >> 3) % 7), r: (v % 8) * 45 };
  });

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label={label ?? (text && name ? `${name}'s avatar` : "Anonymous donor")}
      className="shrink-0"
    >
      <rect width="100" height="100" fill={sc.bg} />
      <g fill="none" stroke={sc.doodle} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {doodles.map((d, i) => (
          <path key={i} d={d.d} transform={`translate(${d.x} ${d.y}) rotate(${d.r} 12 12) scale(1.15)`} />
        ))}
      </g>
      {dots.length > 0 ? (
        <g fill={sc.fg}>
          {dots.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={cell * 0.38} />
          ))}
        </g>
      ) : (
        // Anonymous: a single dot-matrix heart
        <g fill={sc.fg}>
          {["01010", "11111", "11111", "01110", "00100"].flatMap((row, r) =>
            [...row].map((b, c) => (b === "1" ? <circle key={`${r}-${c}`} cx={35 + c * 7.5} cy={36 + r * 7.5} r={2.8} /> : null)),
          )}
        </g>
      )}
    </svg>
  );
}
