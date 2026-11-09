import Link from "next/link";
import { GlobeBackdrop, type GlobePin } from "./GlobeBackdrop";

// Krowd page-title band: dark band below the header, title left, breadcrumb right, mint corner bottom-left.
// With `globe`, a dimmed turning globe rises from the bottom of the band (F1-intro style), with
// project pins to hover; it fills the band's empty middle on pages with little above the fold.
export function PageTitle({ title, crumb, globe, main = true }: { title: string; crumb: string; globe?: GlobePin[]; main?: boolean }) {
  const H = main ? "h1" : "p";
  return (
    <section className="relative mt-20 overflow-hidden bg-ink bg-[linear-gradient(135deg,#0b2e33_0%,#005a73_60%,#007190_100%)] lg:mt-[110px]">
      <div className="container-k relative z-10 flex pointer-events-none [&_a]:pointer-events-auto min-h-[200px] flex-wrap items-center justify-between gap-4 py-10 lg:min-h-[330px]">
        <H className="font-display text-4xl text-white lg:text-6xl">{title}</H>
        <nav aria-label="Breadcrumb" className="text-lg font-medium text-white">
          <Link href="/" className="hover:text-accent">
            Home
          </Link>
          <span className="mx-2" aria-hidden>
            /
          </span>
          <span aria-current="page">{crumb}</span>
        </nav>
      </div>
      {globe && globe.length > 0 && (
        <div className="pointer-events-none absolute inset-y-0 left-1/2 hidden w-[min(560px,46vw)] -translate-x-[20%] md:block">
          <div className="pointer-events-auto absolute inset-x-0 top-6 [mask-image:linear-gradient(to_bottom,black_55%,transparent_88%)]">
            <GlobeBackdrop pins={globe} />
          </div>
        </div>
      )}
      <span className="absolute bottom-0 left-0 size-[37px] bg-accent" aria-hidden />
    </section>
  );
}
