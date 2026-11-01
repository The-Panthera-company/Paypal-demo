import Link from "next/link";

// Krowd page-title band: dark band below the header, title left, breadcrumb right, mint corner bottom-left.
export function PageTitle({ title, crumb }: { title: string; crumb: string }) {
  return (
    <section className="relative mt-20 bg-ink bg-[linear-gradient(135deg,#1b192c_0%,#2e009c_60%,#4319cc_100%)] lg:mt-[110px]">
      <div className="container-k flex min-h-[200px] flex-wrap items-center justify-between gap-4 py-10 lg:min-h-[330px]">
        <h1 className="text-4xl text-white lg:text-6xl">{title}</h1>
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
      <span className="absolute bottom-0 left-0 size-[37px] bg-accent" aria-hidden />
    </section>
  );
}
