import { NextRequest, NextResponse } from "next/server";

import { TOKEN_COOKIE_NAME } from "@/lib/auth/session";

const PUBLIC_PATHS = new Set(["/login"]);

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get(TOKEN_COOKIE_NAME)?.value;

  if (PUBLIC_PATHS.has(pathname)) {
    if (token) {
      const url = req.nextUrl.clone();
      url.pathname = "/dashboard";
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/|.*\\.svg$|.*\\.png$).*)",
  ],
};
