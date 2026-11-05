// SAMPLE team data for project pages, until the research report (Person 3's agents) supplies the
// real project lead, members and their public social links. Replace `getProjectTeam` with a call
// to that report; the page only needs this shape. Names and handles here are fictional.
import type { Project } from "./types";

export type TeamMember = {
  name: string;
  role: string;
  lead?: boolean;
  bio: string;
  /** url is empty for sample data, which is never linked (a made-up handle may belong to a real person) */
  socials: { kind: "x" | "linkedin" | "instagram" | "web"; handle: string; url: string }[];
};

const PEOPLE = [
  "Amina Wanjiru", "Brian Otieno", "Grace Muthoni", "Kofi Mensah", "Lucia Silva", "Rahim Chowdhury",
  "Esther Achieng", "Diego Ramos", "Mei Lin", "Joseph Kamau", "Farah Khan", "Samuel Kiprono",
];

const ROLES: Record<string, string[]> = {
  education: ["Head teacher", "Librarian", "Parent committee chair", "Volunteer tutor"],
  health: ["Clinical officer", "Community health worker", "Nurse", "Logistics volunteer"],
  environment: ["Field coordinator", "Youth group leader", "Nursery manager", "Volunteer"],
  water: ["Water committee chair", "Pump mechanic", "Treasurer", "Community mobiliser"],
};

const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 11);
const slug = (s: string) => s.toLowerCase().replace(/[^a-z]+/g, "");

/** Sample roster: a lead and 2-3 members, stable per project */
export function getProjectTeam(p: Project): { sample: true; members: TeamMember[] } {
  const h = hash(p.id + p.title);
  const roles = ROLES[p.categoryId] ?? ROLES.education;
  const size = 3 + (h % 2);
  const members: TeamMember[] = Array.from({ length: size }, (_, i) => {
    const name = PEOPLE[(h + i * 5) % PEOPLE.length];
    const handle = slug(name);
    const lead = i === 0;
    const role = lead ? "Project lead" : roles[(h + i) % roles.length];
    const socials: TeamMember["socials"] = [
      { kind: "linkedin", handle: name, url: "" },
      { kind: "x", handle: `@${handle}`, url: "" },
    ];
    if (lead) socials.push({ kind: "instagram", handle: `@${slug(p.title)}`, url: "" });
    return {
      name,
      role,
      lead,
      bio: lead
        ? `Started ${p.title} and reports on every milestone.`
        : `${role} in ${p.facets.region}, helping run ${p.title}.`,
      socials,
    };
  });
  return { sample: true, members };
}
