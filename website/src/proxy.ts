import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/mgmt") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/catalog") ||
    pathname.startsWith("/brand") ||
    pathname.startsWith("/screenshots")
  ) {
    return NextResponse.next();
  }

  let locale = "en";
  let bare = pathname;
  if (pathname === "/he" || pathname.startsWith("/he/")) {
    locale = "he";
    bare = pathname.slice(3) || "/";
  } else if (pathname === "/en" || pathname.startsWith("/en/")) {
    bare = pathname.slice(3) || "/";
  }

  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${bare === "/" ? "" : bare}`;
  const headers = new Headers(request.headers);
  headers.set("x-vital-locale", locale);
  headers.set("x-vital-path", bare);
  return NextResponse.rewrite(url, { request: { headers } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|.*\\..*).*)"],
};
