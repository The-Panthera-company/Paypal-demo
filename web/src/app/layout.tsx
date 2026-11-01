import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Community Giving",
  description: "The group decides where the money goes; agents protect it; rules keep it fair; PayPal moves the money.",
};

const nav = [
  { href: "/projects", label: "Projects" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/mandate", label: "My Giving Agent" },
  { href: "/report", label: "My Impact" },
  { href: "/admin", label: "Admin" },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-black/10 dark:border-white/10">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-4">
            <Link href="/" className="text-lg font-semibold">
              Community Giving
            </Link>
            {nav.map((item) => (
              <Link key={item.href} href={item.href} className="text-sm opacity-80 hover:opacity-100">
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
