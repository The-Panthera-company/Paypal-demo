"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const nav = [
  { href: "/", label: "Home" },
  { href: "/projects", label: "Explore" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/mandate", label: "Giving Agent" },
  { href: "/report", label: "My Impact" },
  { href: "/admin", label: "Admin" },
];

// Krowd Home 2 header: transparent over the hero, navy and fixed after 160 px of scroll;
// below 992 px a hamburger opens a 290 px off-canvas panel from the left.
export function Header() {
  const pathname = usePathname();
  const overHero = pathname === "/";
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 160);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const solid = scrolled || !overHero;

  return (
    <>
      <header
        className={`inset-x-0 top-0 z-30 border-b border-white/15 transition-all duration-300 ${
          solid ? "fixed bg-ink shadow-lg" : "absolute bg-transparent"
        }`}
      >
        <div className="flex h-20 items-center px-4 lg:h-[110px] lg:px-20">
          <Link href="/" className="flex items-center gap-3 pr-6 text-white lg:border-r lg:border-white/15 lg:pr-10 lg:h-full">
            <span className="corner grid size-10 place-items-center bg-brand font-display text-xl" style={{ ["--corner-size" as string]: "10px" }} aria-hidden>
              C
            </span>
            <span className="font-display text-2xl">Community Giving</span>
          </Link>

          <nav aria-label="Main" className="hidden flex-1 lg:block">
            <ul className="flex justify-center">
              {nav.map((n) => {
                const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
                return (
                  <li key={n.href}>
                    <Link
                      href={n.href}
                      aria-current={active ? "page" : undefined}
                      className={`mx-3 block leading-[110px] transition-colors xl:mx-5 ${active ? "text-accent" : "text-white hover:text-accent"}`}
                    >
                      {n.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="ml-auto hidden h-full items-center border-l border-white/15 pl-10 lg:flex">
            <Link href="/projects" className="btn">
              Back a project
            </Link>
          </div>

          <button
            type="button"
            onClick={() => setOpen(true)}
            className="ml-auto grid size-12 place-items-center text-white lg:hidden"
            aria-label="Open menu"
            aria-expanded={open}
            aria-controls="offcanvas"
          >
            <svg width="26" height="20" viewBox="0 0 26 20" fill="currentColor" aria-hidden>
              <rect width="26" height="2" />
              <rect y="9" width="26" height="2" />
              <rect y="18" width="26" height="2" />
            </svg>
          </button>
        </div>
      </header>

      <div
        className={`fixed inset-0 z-40 bg-ink/60 transition-opacity lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        id="offcanvas"
        className={`fixed inset-y-0 left-0 z-50 w-[290px] bg-white p-6 transition-transform duration-300 lg:hidden ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-label="Menu"
        aria-hidden={!open}
      >
        <button type="button" onClick={() => setOpen(false)} className="mb-6 ml-auto grid size-12 place-items-center text-ink" aria-label="Close menu" tabIndex={open ? 0 : -1}>
          <svg width="20" height="20" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M2 2l16 16M18 2L2 18" />
          </svg>
        </button>
        <ul>
          {nav.map((n) => (
            <li key={n.href} className="border-b border-line">
              <Link href={n.href} className="flex min-h-12 items-center text-sm text-ink" tabIndex={open ? 0 : -1}>
                {n.label}
              </Link>
            </li>
          ))}
        </ul>
        <Link href="/projects" className="btn mt-6 w-full" tabIndex={open ? 0 : -1}>
          Back a project
        </Link>
      </aside>
    </>
  );
}
