import type { TeamMember } from "@/lib/project-team";
import { Avatar } from "./Avatar";

const ICON: Record<TeamMember["socials"][number]["kind"], string> = {
  x: "M4 4l16 16M20 4L4 20",
  linkedin: "M4 9h4v11H4zM6 4a2 2 0 110 4 2 2 0 010-4zM11 9h4v2c1-2 6-3 6 3v6h-4v-5c0-2-3-2-3 0v5h-3z",
  instagram: "M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2zM12 8a4 4 0 100 8 4 4 0 000-8zM17.5 6.5h.01",
  web: "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
};

// Team roster: hovering (or tabbing into) a member blurs the picture and slides in a padded panel
// with their role and public social links (from the project's research report; sample for now).
export function TeamRoster({ members, sample }: { members: TeamMember[]; sample?: boolean }) {
  return (
    <div className="space-y-4">
      {sample && <p className="text-sm">Sample team. The real roster comes from the project&apos;s research report.</p>}
      <ul className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {members.map((m) => (
          <li key={m.name} className="group relative aspect-[3/4] overflow-hidden bg-ink focus-within:ring-4 focus-within:ring-accent">
            <div className="size-full transition-[filter,transform] duration-500 group-focus-within:scale-105 group-focus-within:blur-[3px] group-hover:scale-105 group-hover:blur-[3px] [&_svg]:size-full">
              <Avatar name={m.name} seed={m.name} size={300} label={`${m.name}, ${m.role}`} />
            </div>
            {/* Always visible: name and role */}
            <div className="absolute inset-x-0 bottom-0 bg-[linear-gradient(transparent,rgba(11,46,51,0.9))] p-4 pt-10 text-white transition-opacity duration-300 group-focus-within:opacity-0 group-hover:opacity-0">
              {m.lead && <span className="mb-1 inline-block bg-accent px-2 text-[10px] font-bold uppercase leading-5 tracking-[2px] text-ink">Lead</span>}
              <p className="font-display text-xl leading-6">{m.name}</p>
              <p className="text-sm text-cobalt-green">{m.role}</p>
            </div>
            {/* Slides in on hover/focus */}
            <div className="absolute inset-3 flex translate-y-6 flex-col justify-end overflow-hidden bg-white/95 p-5 text-ink opacity-0 shadow-lg transition-all duration-500 group-focus-within:translate-y-0 group-focus-within:opacity-100 group-hover:translate-y-0 group-hover:opacity-100">
              <p className="font-display text-xl leading-6">{m.name}</p>
              <p className="text-sm font-medium text-primary">{m.role}</p>
              <p className="mt-2 text-sm leading-5">{m.bio}</p>
              <p className="mt-3 truncate text-xs">{m.socials.find((x) => x.kind === "x")?.handle}</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {m.socials.map((s) => (
                  <li key={s.kind}>
                    {(() => {
                      const label = `${m.name} on ${s.kind === "x" ? "X" : s.kind[0].toUpperCase() + s.kind.slice(1)}: ${s.handle}`;
                      const cls = "grid size-10 place-items-center border border-line";
                      const body = (
                        <>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                            <path d={ICON[s.kind]} />
                          </svg>
                          
                        </>
                      );
                      return s.url ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className={`${cls} hover:border-primary hover:text-primary`} aria-label={label} title={label}>
                          {body}
                        </a>
                      ) : (
                        <span className={cls} role="img" aria-label={label} title={label}>
                          {body}
                        </span>
                      );
                    })()}
                  </li>
                ))}
              </ul>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
