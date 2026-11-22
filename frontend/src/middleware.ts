import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const SESSION_COOKIE_NAME = "shipproof_session";

function getSessionSecret(): string {
  return (
    process.env.SESSION_SECRET ||
    process.env.SHIPPROOF_BACKEND_API_KEY ||
    process.env.SHIPPROOF_API_KEY ||
    "shipproof_dev_session_secret_do_not_use_in_prod_12345678"
  );
}

function isAuthRequired(): boolean {
  return Boolean(
    process.env.SHIPPROOF_BETA_KEY ||
    process.env.SHIPPROOF_BACKEND_API_KEY ||
    process.env.SHIPPROOF_API_KEY
  );
}

async function verifyToken(tokenString?: string | null): Promise<boolean> {
  if (!tokenString) return false;

  try {
    const parts = tokenString.split(".");
    if (parts.length !== 2) return false;

    const [payloadB64, sigHex] = parts;
    const secret = getSessionSecret();

    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );

    const expectedSigBuf = await crypto.subtle.sign("HMAC", key, enc.encode(payloadB64));
    const expectedSigHex = Array.from(new Uint8Array(expectedSigBuf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

    if (sigHex !== expectedSigHex) return false;

    // Decode base64url payload
    const binStr = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(binStr);
    const now = Math.floor(Date.now() / 1000);
    return payload.exp > now;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow Next.js static assets, images, background, favicon, and demo store routes
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon.ico") ||
    pathname.startsWith("/images") ||
    pathname === "/background.jpg" ||
    pathname.startsWith("/store") ||
    pathname.startsWith("/cart") ||
    pathname.startsWith("/checkout") ||
    pathname.startsWith("/order-confirmation") ||
    pathname.startsWith("/product") ||
    pathname.startsWith("/static") ||
    /\.(jpe?g|png|svg|webp|ico|gif)$/i.test(pathname)
  ) {
    return NextResponse.next();
  }

  // Allow BFF auth endpoints, public health check, and diagnostic endpoint without session check
  if (
    pathname === "/api/health" ||
    pathname === "/api/diag" ||
    pathname.startsWith("/api/auth/login") ||
    pathname.startsWith("/api/auth/session")
  ) {
    return NextResponse.next();
  }

  const authRequired = isAuthRequired();
  const sessionCookie = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  const isAuthenticated = authRequired ? await verifyToken(sessionCookie) : true;

  // Handle Login Page access
  if (pathname === "/login") {
    if (isAuthenticated && authRequired) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  // If unauthenticated in protected mode
  if (!isAuthenticated) {
    if (pathname.startsWith("/api")) {
      return NextResponse.json(
        { detail: "Authentication required: please log in to access the beta environment." },
        { status: 401 }
      );
    }
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // CSRF Mitigation for mutating requests originating from browser
  const method = request.method.toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const origin = request.headers.get("origin");
    const host = request.headers.get("host");
    const secFetchSite = request.headers.get("sec-fetch-site");

    // If origin is present, ensure it matches host (prevent cross-site form post)
    if (origin && host) {
      try {
        const originHost = new URL(origin).host;
        if (originHost !== host) {
          return NextResponse.json(
            { detail: "Cross-site request forgery protection: origin mismatch rejected." },
            { status: 403 }
          );
        }
      } catch {
        return NextResponse.json({ detail: "Invalid request origin." }, { status: 403 });
      }
    }

    if (secFetchSite === "cross-site") {
      return NextResponse.json(
        { detail: "Cross-site mutating requests strictly prohibited." },
        { status: 403 }
      );
    }
  }

  // For authenticated requests to backend API, inject master Bearer token if configured
  if (pathname.startsWith("/api")) {
    const backendKey =
      process.env.SHIPPROOF_BACKEND_API_KEY ||
      process.env.SHIPPROOF_API_KEY;

    if (backendKey) {
      const requestHeaders = new Headers(request.headers);
      requestHeaders.set("Authorization", `Bearer ${backendKey}`);
      return NextResponse.next({
        request: {
          headers: requestHeaders,
        },
      });
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
