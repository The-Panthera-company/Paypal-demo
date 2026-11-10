import { RollingNumber } from "./RollingNumber";
import Link from "next/link";

const art: Record<string, { from: string; to: string; label: string }> = {
  health: { from: "#b4533a", to: "#0b2e33", label: "Health" },
  education: { from: "#7a5c2e", to: "#0b2e33", label: "Education" },
  environment: { from: "#2f7d4f", to: "#0b2e33", label: "Environment" },
  water: { from: "#007190", to: "#0b2e33", label: "Water" },
};

// Free Unsplash photos (Unsplash licence), loaded by the visitor's browser. Placeholders until
// projects upload their own photos. Several per category so cards don't repeat.
const u = (id: string) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=640&q=55`;
export const PHOTOS: Record<string, string[]> = {
  health: [u("1576091160550-2173dba999ef"), u("1584515933487-779824d29309"), u("1579684385127-1ef15d508118")],
  education: [u("1503676260728-1c00da094a0b"), u("1497633762265-9d179a990aa6"), u("1509062522246-3755977927d7")],
  environment: [u("1542601906990-b4d3fb778b09"), u("1466692476868-aef1dfb1e735"), u("1500382017468-9049fed747ef")],
  water: [u("1509099836639-18ba1795216e"), u("1541544537156-7627a7a4aa1c"), u("1559825481-12a05cc00344")],
  people: [u("1488521787991-ed7bbaae773c"), u("1559027615-cd4628902d4a"), u("1532629345422-7515f3d16bb6")],
};

/** Stable choice: the same project always gets the same photo */
export function photoFor(categoryId: string, seed = "") {
  const list = PHOTOS[categoryId] ?? PHOTOS.people;
  const n = [...seed].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 0);
  return list[n % list.length];
}

/** Give each project its own photo: within a category, no two projects share one until the list runs out */
// Demo-video branch: a fitting photo per project, by title (files in public/demo)
const d = (f: string) => `/demo/${f}.jpg`;
export const DEMO_PHOTOS: Record<string, string> = {
  "Bhote Koshi Clean Water Filters": d("water-hands"),
  "Tatopani Temporary Footbridge": d("bridge-nepal"),
  "Sindhupalchok Mobile Flood Clinic": d("clinic-nepal-2"),
  "Nyando Flood Medical Outreach": d("flood-street"),
  "Back to School after the Nyando Floods": d("classroom"),
  "Lara Earthquake First Aid Posts": d("first-aid"),
  "White Nile Emergency Shelter Kits": d("shelter-rain"),
  "Cox's Bazar Flood Water Points": d("water-tap-kids"),
  "Nyando Riverbank Replanting": d("seedlings"),
  "Village Borehole Repair": d("hand-pump-sudan"),
  "School Rainwater Tanks": d("water-tap-bucket"),
  "Idlib Mobile Maternity Unit": d("camp-aerial"),
  "Lesbos Refugee Winter Kits": d("winter-blanket"),
  "Faith Community Food Pantry, Detroit": d("food-bags"),
  "Lanet Library": d("reading-group"),
  "New Reading Corner": d("reading-tutor"),
  "Mobile Eye Clinic": d("clinic-nepal"),
};

export function assignPhotos(projects: { id: string; categoryId: string; title?: string }[]): Record<string, string> {
  const used: Record<string, Set<number>> = {};
  const out: Record<string, string> = {};
  for (const p of projects) {
    if (p.title && DEMO_PHOTOS[p.title]) {
      out[p.id] = DEMO_PHOTOS[p.title];
      continue;
    }
    const list = PHOTOS[p.categoryId] ?? PHOTOS.people;
    const seen = (used[p.categoryId] ??= new Set());
    if (seen.size >= list.length) seen.clear();
    let i = [...p.id].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 0) % list.length;
    while (seen.has(i)) i = (i + 1) % list.length;
    seen.add(i);
    out[p.id] = list[i];
  }
  return out;
}

/** Project image: a photo with a soft teal tint over the category colour (shown alone if the photo can't load) */
export function CategoryArt({ id, seed = "", label, photo, tint = true }: { id: string; seed?: string; label?: string; photo?: string; tint?: boolean }) {
  const a = art[id] ?? art.education;
  const src = photo ?? photoFor(id, seed);
  return (
    <div
      role="img"
      aria-label={label ?? `${a.label} project photo`}
      className="relative size-full bg-cover bg-center"
      style={{ backgroundImage: `url("${src}"), linear-gradient(135deg, ${a.from}, ${a.to})` }}
    >
      {tint && <span className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,113,144,0.10),rgba(11,46,51,0.45))]" aria-hidden />}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} className="h-[9px] bg-line">
      <div className="h-full bg-growth" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Eyebrow({ children, dark = false }: { children: React.ReactNode; dark?: boolean }) {
  return (
    <div className="mb-3">
      <p className={`eyebrow ${dark ? "!text-brand-tint" : ""}`}>{children}</p>
    </div>
  );
}

/** Krowd stat box: white square, big violet number, small label */
export function StatBox({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col justify-center bg-white p-5 text-center shadow-[0_0_30px_rgba(0,0,0,0.05)]">
      <div className="text-2xl font-bold text-brand">
        <RollingNumber value={value} />
      </div>
      <div className="text-sm">{label}</div>
    </div>
  );
}

/** Empty state: says what happened and offers a next step */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: { href: string; label: string } }) {
  return (
    <div className="border border-dashed border-line bg-white p-10 text-center">
      <p className="font-display text-2xl text-ink">{title}</p>
      <p className="mt-2">{body}</p>
      {action && (
        <Link href={action.href} className="btn btn-2 mt-6">
          {action.label}
        </Link>
      )}
    </div>
  );
}
