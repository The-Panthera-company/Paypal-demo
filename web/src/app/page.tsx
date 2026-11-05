import Link from "next/link";
import { GivingAssistant } from "@/components/GivingAssistant";
import { ImpactGallery } from "@/components/ImpactGallery";
import { FeaturedStrip } from "@/components/FeaturedStrip";
import { BackerStories, SponsorStrip } from "@/components/Sections";
import { Countdown } from "@/components/Countdown";
import { categoryIcon, Icon } from "@/components/Icon";
import { assignPhotos, CategoryArt, Eyebrow, photoFor } from "@/components/ui";
import { daysLeft, formatDate, formatMoney, getBackerStories, getCategories, getImpactUpdates, getProjects, getRound, getSponsors } from "@/lib/api";

const faqs = [
  ["How does matching work?", "A sponsor pool is shared by quadratic funding: a project backed by many people gets a bigger top-up than one backed by a few large gifts. Caps stop any single project taking everything."],
  ["When does a project get the money?", "Your gift goes to the project you chose. Matching money is released in tranches, only after the project uploads receipts and photos that pass our checks."],
  ["What does the Giving Agent do?", "It donates your monthly budget for you, within the rules you set: causes, exclusions and a limit per project. It explains every choice, and gifts above your threshold wait for your approval."],
  ["How are projects verified?", "Every project shows its registration documents and plan. An admin approves it before it is listed, and a watchdog freezes matching if it spots suspicious donation patterns."],
];

const steps = [
  ["hand", "Choose", "Back a project, a whole category, or let your Giving Agent choose within your rules."],
  ["scale", "Match", "The sponsor pool multiplies small gifts. The more people back a project, the bigger its share."],
  ["receipt", "See the proof", "Money is released with receipts and photos, and your impact report shows where every dollar went."],
];

export default async function Home() {
  const [projects, categories, updates, stories, sponsors, round] = await Promise.all([
    getProjects(),
    getCategories(),
    getImpactUpdates(),
    getBackerStories(),
    getSponsors(),
    getRound(),
  ]);
  const galleryItems = updates.slice(0, 3).map((u) => ({ ...u, project: projects.find((p) => p.id === u.projectId) }));
  const dateLabels = Object.fromEntries(updates.map((u) => [u.id, formatDate(u.date)]));
  const raised = projects.reduce((s, p) => s + p.raised.amount, 0);
  const backers = projects.reduce((s, p) => s + p.backerCount, 0);
  const featured = [...projects].sort((a, b) => b.urgency - a.urgency).slice(0, 5);
  const photos = assignPhotos(featured);

  return (
    <>
      {/* Hero: one static slide, two actions */}
      <section className="relative flex min-h-[560px] items-center overflow-hidden bg-ink pb-16 pt-32 lg:min-h-[640px] lg:pt-[110px]">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url("${photoFor("people", "hero")}")` }}
          aria-hidden
        />
        <div className="absolute inset-0 bg-[linear-gradient(110deg,rgba(11,46,51,0.96)_25%,rgba(0,113,144,0.85)_65%,rgba(0,151,141,0.7)_100%)]" aria-hidden />
        <div className="absolute -right-20 top-1/4 hidden size-[420px] border border-white/10 lg:block" aria-hidden />
        <div className="absolute right-32 top-1/3 hidden size-[300px] border border-white/10 lg:block" aria-hidden />
        <div className="container-k relative flex flex-wrap items-center justify-between gap-12">
          <div className="max-w-[720px]">
            <span className="corner mb-8 block size-[46px] bg-brand" style={{ ["--corner-size" as string]: "17px" }} aria-hidden />
            <p className="mb-5 inline-block border-b border-white/40 pb-1 text-xl text-white">Giving decided by the crowd</p>
            <h1 className="mb-10 text-4xl leading-[46px] text-white lg:text-[78px] lg:leading-[88px]">Small gifts, decided together</h1>
            <div className="flex flex-wrap gap-4">
              <Link href="/projects" className="btn">
                Back a project
              </Link>
              <Link href="/mandate" className="btn btn-2 border border-white/30">
                Set up a Giving Agent
              </Link>
            </div>
          </div>
          <Countdown endsAt={round.endsAt} />
        </div>
      </section>

      {/* About, with real platform totals */}
      <section className="section">
        <div className="container-k grid items-center gap-12 lg:grid-cols-2">
          <div className="relative hidden pl-10 lg:block">
            <span className="absolute left-0 top-0 h-[200px] w-[30px] bg-cobalt-green" aria-hidden />
            <span className="absolute bottom-0 left-0 h-[200px] w-[30px] bg-brand" aria-hidden />
            <div className="aspect-[4/5]">
              <CategoryArt id="people" seed="about" label="Volunteers working together on a community project" />
            </div>
          </div>
          <div>
            <Eyebrow>Why it works</Eyebrow>
            <h2 className="section-title mb-6">Every voice counts, every dollar is traced</h2>
            <p className="mb-6 text-lg leading-9">
              Big donors usually decide where charity money goes. Here, the number of people who back a project matters
              more than the size of any single gift.
            </p>
            <ul className="mb-8 space-y-2 text-lg">
              {["Verified projects only", "Matching that rewards many backers", "Payouts released with receipts"].map((t) => (
                <li key={t} className="flex items-center gap-3 text-ink">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-brand)" strokeWidth="3" aria-hidden>
                    <path d="M4 12l5 5L20 6" />
                  </svg>
                  {t}
                </li>
              ))}
            </ul>
            <div className="mb-8 grid grid-cols-3 gap-px bg-brand-line">
              {[
                [formatMoney({ amount: raised, currency: "USD" }), "raised"],
                [String(backers), "backers"],
                [String(projects.length), "projects"],
              ].map(([v, l], i) => (
                <div key={l} className={`bg-brand p-4 text-center text-white lg:p-6 ${i === 2 ? "corner" : ""}`} style={{ ["--corner-size" as string]: "23px" }}>
                  <div className="tabular font-display text-2xl lg:text-4xl">{v}</div>
                  <div className="text-sm text-brand-tint">{l}</div>
                </div>
              ))}
            </div>
            <Link href="/projects" className="btn btn-2">
              Discover projects
            </Link>
          </div>
        </div>
      </section>

      {/* Explore projects: static grid on a light band */}
      <section className="relative pb-16 lg:pb-[120px]">
        <div className="absolute inset-x-0 top-0 h-[480px] bg-surface-alt lg:h-[602px]" aria-hidden />
        <div className="container-k relative pt-16 lg:pt-[110px]">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div>
              <Eyebrow>Urgent and overlooked first</Eyebrow>
              <h2 className="section-title">Explore projects</h2>
            </div>
            <nav aria-label="Categories" className="flex flex-wrap gap-2">
              {categories.map((c) => (
                <Link
                  key={c.id}
                  href={`/projects?category=${c.id}`}
                  className="flex min-h-11 items-center gap-2 border border-line bg-white px-4 text-sm text-ink hover:border-brand hover:text-brand"
                >
                  <Icon name={categoryIcon[c.id] ?? "heart"} size={18} className="text-growth" />
                  {c.name}
                </Link>
              ))}
            </nav>
          </div>
          <FeaturedStrip
            items={featured.map((p) => ({ project: p, photo: photos[p.id], raised: formatMoney(p.raised), goal: formatMoney(p.goal), days: daysLeft(p) }))}
          />
          <div className="mt-10 text-center">
            <Link href="/projects" className="btn btn-2">
              See all projects
            </Link>
          </div>
        </div>
      </section>

      {/* FAQ on a dark band */}
      <section id="faq" className="bg-ink bg-[linear-gradient(135deg,#0b2e33,#005a73)] py-16 lg:py-[120px]">
        <div className="container-k grid gap-12 lg:grid-cols-2">
          <div>
            <Eyebrow dark>Questions</Eyebrow>
            <h2 className="section-title mb-6 text-white">How can we help?</h2>
            <p className="mb-8 text-brand-tint">Short answers about matching, payouts and safety. Ask the assistant on any project page for more.</p>
            <div className="grid grid-cols-3 gap-4">
              {[
                ["users", "Backers"],
                ["project", "Projects"],
                ["card", "Payments"],
              ].map(([icon, t]) => (
                <div key={t} className="group corner border border-brand bg-white p-4 text-center transition-shadow hover:shadow-lg" style={{ ["--corner-size" as string]: "0px" }}>
                  <Icon name={icon} size={40} className="mx-auto mb-2 text-brand" />
                  <div className="text-ink">{t}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            {faqs.map(([q, a], i) => (
              <details key={q} name="faq" className="group bg-white/5 px-6 py-6 open:border open:border-brand-line lg:px-[38px]" open={i === 0}>
                <summary className="flex cursor-pointer list-none items-center gap-3 text-lg font-medium text-white">
                  <span className="font-display text-accent">{i + 1}.</span>
                  <span className="flex-1">{q}</span>
                  <span className="text-2xl text-accent group-open:rotate-45 transition-transform" aria-hidden>
                    +
                  </span>
                </summary>
                <p className="mt-4 text-brand-tint">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Impact gallery preview: proof from released milestones */}
      {galleryItems.length > 0 && (
      <section className="section">
        <div className="container-k">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div>
              <Eyebrow>Proof, not promises</Eyebrow>
              <h2 className="section-title">Latest impact</h2>
            </div>
            <Link href="/gallery" className="font-medium text-brand underline-offset-4 hover:underline">
              See the full gallery
            </Link>
          </div>
          <ImpactGallery items={galleryItems} dateLabels={dateLabels} />
        </div>
      </section>
      )}

      <BackerStories stories={stories} projects={projects} />

      {/* How it works: 3 numbered steps */}
      <section id="how-it-works" className="section bg-surface-alt">
        <div className="container-k">
          <div className="mb-10 text-center">
            <Eyebrow>How it works</Eyebrow>
            <h2 className="section-title">Three steps, full transparency</h2>
          </div>
          <ol className="grid gap-[30px] md:grid-cols-3">
            {steps.map(([icon, t, d], i) => (
              <li key={t} className="corner bg-white p-10 transition-shadow hover:shadow-[0_0_30px_rgba(0,0,0,0.05)]">
                <div className="mb-4 flex items-center justify-between">
                  <Icon name={icon} size={44} className="text-growth" />
                  <span className="font-display text-5xl text-brand">0{i + 1}</span>
                </div>
                <h3 className="mb-3 text-2xl">{t}</h3>
                <p className="leading-[30px]">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Together CTA band */}
      <section className="relative bg-ink py-20 text-center lg:py-28">
        <div className="absolute inset-0 bg-[linear-gradient(135deg,#00978d,#0b2e33)] opacity-90" aria-hidden />
        <div className="container-k relative">
          <p className="mb-4 text-xl text-accent">Start small</p>
          <h2 className="section-title mx-auto mb-10 max-w-3xl text-white">Together we decide where the good goes</h2>
          <Link href="/projects" className="btn">
            Back a project
          </Link>
        </div>
      </section>

      <SponsorStrip sponsors={sponsors} />
      <GivingAssistant projects={projects} />
    </>
  );
}
