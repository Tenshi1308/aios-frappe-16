import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const host = req.headers.get("host") ?? "";
  const isDevPort = host.includes(":8085");
  const { pathname } = req.nextUrl;

  // Jika pengunjung masuk lewat Port 8085 (Developer)
  if (isDevPort) {
    if (pathname === "/" || pathname === "/login") {
      return NextResponse.redirect(new URL("/developer/login", req.url));
    }
  }

  // Jika pengunjung masuk lewat Port 8084 (Client)
  if (!isDevPort) {
    if (pathname.startsWith("/developer")) {
      return NextResponse.redirect(new URL("/login", req.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon.ico).*)"],
};