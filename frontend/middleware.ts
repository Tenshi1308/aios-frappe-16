import { NextResponse, type NextRequest } from "next/server";

// Portal terpisah via domain (architecture.md §8):
//   client.localhost:4001    → halaman portal client
//   developer.localhost:4001 → halaman portal monitoring Ekasa Developer
// Di lokal, *.localhost otomatis resolve ke 127.0.0.1 di browser modern.
export function middleware(req: NextRequest) {
  const host = (req.headers.get("host") ?? "").toLowerCase();
  const isDeveloper = host.startsWith("developer.");
  const { pathname } = req.nextUrl;

  if (isDeveloper && !pathname.startsWith("/developer")) {
    return NextResponse.rewrite(new URL(`/developer${pathname === "/" ? "" : pathname}`, req.url));
  }
  if (!isDeveloper && pathname.startsWith("/developer")) {
    return NextResponse.rewrite(new URL(pathname.replace(/^\/developer/, "") || "/", req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon.ico).*)"],
};
