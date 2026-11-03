import Link from "next/link";

const columns = [
  {
    title: "Platform",
    links: [
      ["/projects", "Explore projects"],
      ["/gallery", "Impact gallery"],
      ["/leaderboard", "Leaderboard"],
      ["/mandate", "Giving Agent"],
      ["/report", "My impact"],
    ],
  },
  {
    title: "How it works",
    links: [
      ["/#how-it-works", "Matching pool"],
      ["/#faq", "Fees and payouts"],
      ["/#faq", "Verification"],
      ["/#faq", "Privacy"],
    ],
  },
];

export function Footer() {
  return (
    <footer className="bg-ink pt-16 text-footer-text lg:pt-[90px]">
      <div className="container-k grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-4">
          <div className="font-display text-2xl text-white">Community Giving</div>
          <p>
            Small donors decide together. AI agents check every step, fixed rules move the money, and PayPal handles
            every payment.
          </p>
        </div>
        {columns.map((c) => (
          <div key={c.title}>
            <h2 className="mb-4 text-xl text-white">{c.title}</h2>
            <ul>
              {c.links.map(([href, label]) => (
                <li key={label}>
                  <Link href={href} className="leading-9 transition-colors hover:text-brand-tint">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <form className="space-y-3" action="#" aria-labelledby="newsletter-title">
          <h2 id="newsletter-title" className="text-xl text-white">
            Impact updates
          </h2>
          <label htmlFor="newsletter-email" className="block text-sm">
            Email address
          </label>
          <div className="flex border border-[#312e42]">
            <input
              id="newsletter-email"
              type="email"
              required
              placeholder="you@example.com"
              className="min-h-14 flex-1 bg-transparent px-4 text-white placeholder:text-footer-text/70 focus:outline-none"
            />
            <button className="grid w-14 place-items-center bg-brand text-white transition-colors hover:bg-accent hover:text-ink" aria-label="Subscribe">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          </div>
          <p className="text-sm">One email a month with receipts from the projects you backed.</p>
        </form>
      </div>
      <div className="mt-16 border-t border-footer-line py-8 text-center text-sm lg:mt-[107px]">
        © 2026 Community Giving · PayPal AI Hackathon demo · Sandbox payments only
      </div>
    </footer>
  );
}
