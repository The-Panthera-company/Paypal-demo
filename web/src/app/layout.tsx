import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Community Giving",
  description: "The group decides where the money goes; agents protect it; rules keep it fair; PayPal moves the money.",
};

const nav = [
  { href: "/projects", label: "Projects" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/mandate", label: "Giving Agent" },
  { href: "/report", label: "My Impact" },
  { href: "/admin", label: "Admin" },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-10 border-b border-line bg-surface/95 backdrop-blur-none">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-1 gap-y-1 px-4 py-2">
            <Link href="/" className="mr-4 flex min-h-11 items-center gap-2 text-lg font-semibold">
              <span className="grid size-7 place-items-center rounded-lg bg-primary text-sm text-white" aria-hidden>
                CG
              </span>
              Community Giving
            </Link>
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex min-h-11 items-center rounded-lg px-3 text-sm text-muted hover:bg-primary-soft hover:text-ink"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
