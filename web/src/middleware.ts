import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const isLoginPage = request.nextUrl.pathname === "/login";
  const isAuthApi = request.nextUrl.pathname.startsWith("/api/auth");
  const authenticated = request.cookies.get("authenticated")?.value === "true";

  if (isAuthApi) return NextResponse.next();

  if (!authenticated && !isLoginPage) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (authenticated && isLoginPage) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
