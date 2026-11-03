import { NextResponse, type NextRequest } from "next/server";

// Locks /admin behind a password when ADMIN_UI_PASSWORD is set (always set it on Render).
// Browser login box (HTTP Basic auth): any user name, the password from the environment.
export function middleware(req: NextRequest) {
  const password = process.env.ADMIN_UI_PASSWORD;
  if (!password) return NextResponse.next();

  const header = req.headers.get("authorization") ?? "";
  const [scheme, encoded] = header.split(" ");
  if (scheme === "Basic" && encoded) {
    const given = atob(encoded).split(":").slice(1).join(":");
    if (given === password) return NextResponse.next();
  }
  return new NextResponse("Admin login required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Community Giving admin"' },
  });
}

export const config = { matcher: ["/admin/:path*"] };
