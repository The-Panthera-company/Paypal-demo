import { NextResponse } from "next/server";
import { getAgentStatus } from "@/lib/admin";

export const dynamic = "force-dynamic";

// Public: only whether agents are paused. The admin token stays on the server; no reason or name leaves.
export async function GET() {
  try {
    const s = await getAgentStatus();
    return NextResponse.json({ paused: s.paused, known: !s.sample }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ paused: false, known: false }, { status: 200 });
  }
}
