import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  // Langsung loloskan semua halaman (baik client maupun developer)
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon.ico).*)"],
};