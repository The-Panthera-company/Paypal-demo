"use server";

import { revalidatePath } from "next/cache";
import { resolveCase, reviewMilestone, verifyProject } from "@/lib/admin";

export type ActionResult = { ok: true; message: string } | { ok: false; message: string };

async function run(fn: () => Promise<void>, done: string): Promise<ActionResult> {
  try {
    await fn();
    revalidatePath("/admin");
    return { ok: true, message: done };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Something went wrong." };
  }
}

export async function verifyAction(id: string, approve: boolean, note?: string) {
  return run(() => verifyProject(id, approve, note), approve ? "Project verified and listed." : "Project sent back to the applicant.");
}

export async function resolveCaseAction(id: string, action: "clear" | "confirm", note?: string) {
  return run(
    () => resolveCase(id, action, note),
    action === "clear" ? "Case cleared: matching resumes." : "Case confirmed: flagged donors now count as one person.",
  );
}

export async function reviewMilestoneAction(id: string, approve: boolean, note?: string) {
  return run(() => reviewMilestone(id, approve, note), approve ? "Tranche released for payout." : "Sent back: the project can upload new evidence.");
}
