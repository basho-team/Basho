import { NextResponse, type NextRequest } from "next/server";
import { mayVisit } from "@/lib/auth/shared";
import { userFromRequest } from "@/lib/auth/session";

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const user = await userFromRequest(request);
  const publicAuth = pathname === "/login" || pathname.startsWith("/api/auth/");
  if (publicAuth) {
    if (pathname === "/login" && user) return NextResponse.redirect(new URL("/", request.url));
    return NextResponse.next();
  }
  if (!user) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ message: "Entre para continuar." }, { status: 401,
        headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (!pathname.startsWith("/api/") && !mayVisit(user.role, pathname)) {
    return NextResponse.redirect(new URL("/acesso-negado", request.url));
  }
  const response = NextResponse.next();
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  matcher: ["/", "/login", "/pesquisador/:path*", "/gerente/:path*", "/fiscal/:path*",
    "/integracoes/:path*", "/acesso-negado", "/api/:path*"],
};
