import { NextRequest, NextResponse } from "next/server";

import { TOKEN_COOKIE_NAME } from "@/lib/auth/session";

const PUBLIC_PATHS = new Set(["/login"]);

/**
 * Build a redirect that PRESERVES the hostname the browser actually used.
 *
 * Next.js dev mode normalizes any URL passed to NextResponse.redirect() —
 * even if you give it a URL object hard-coded to `127.0.0.1`, the response
 * Location header gets rewritten to `localhost`. The only way to keep the
 * incoming hostname is to construct the response manually and set the
 * Location header ourselves.
 *
 * Why this matters: if the user browses to 127.0.0.1:3000 but every redirect
 * sends them to localhost:3000, their auth cookie (scoped to one hostname)
 * is silently invisible after the redirect, and they get stuck in a login
 * loop or a "loading your session…" hang.
 */
function buildRedirect(
  req: NextRequest,
  pathname: string,
  searchParams?: Record<string, string>,
) {
  const incomingHost = req.headers.get("host") ?? req.nextUrl.host;
  const proto =
    req.headers.get("x-forwarded-proto") ??
    req.nextUrl.protocol.replace(":", "");

  let query = "";
  if (searchParams) {
    const usp = new URLSearchParams();
    for (const [k, v] of Object.entries(searchParams)) usp.set(k, v);
    query = `?${usp.toString()}`;
  }
  const fullUrl = `${proto}://${incomingHost}${pathname}${query}`;

  // NOTE: In `next dev` mode, Next.js rewrites the response Location
  // header to its canonical hostname (usually `localhost`) AFTER middleware
  // runs, so even setting it manually here doesn't preserve a different
  // hostname like `127.0.0.1`. In production behind Caddy (or any real
  // reverse proxy), the Host header IS honored and this works correctly.
  // For dev: use one consistent hostname (we recommend `localhost`).
  return new NextResponse(null, {
    status: 307,
    headers: { Location: fullUrl },
  });
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get(TOKEN_COOKIE_NAME)?.value;

  if (PUBLIC_PATHS.has(pathname)) {
    if (token) {
      return buildRedirect(req, "/dashboard");
    }
    return NextResponse.next();
  }

  if (!token) {
    return buildRedirect(req, "/login", { next: pathname });
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Exclude:
    //  - Next.js static assets (_next/static, _next/image)
    //  - The favicon
    //  - Backend API calls (handled by axios with bearer auth)
    //  - SVG/PNG static images
    //  - /go2rtc/* — go2rtc's WebRTC player JS (video-rtc.js + video-stream.js)
    //    served from public/go2rtc/. These must be reachable WITHOUT
    //    login because they load BEFORE React mounts, and they're inert
    //    JS — they don't touch any of our data, just provide the
    //    WebRTC custom element.
    "/((?!_next/static|_next/image|favicon.ico|api/|go2rtc/|.*\\.svg$|.*\\.png$|.*\\.js$).*)",
  ],
};
