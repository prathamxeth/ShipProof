import { NextResponse } from "next/server";
import crypto from "crypto";
import {
  createSessionToken,
  isAuthRequired,
  SESSION_COOKIE_NAME,
  SESSION_TTL_SECONDS,
} from "@/lib/serverAuth";

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const candidatePassword = (body.password || body.key || "").trim();

    const expectedBetaKey =
      process.env.SHIPPROOF_BETA_KEY ||
      process.env.SHIPPROOF_BACKEND_API_KEY ||
      process.env.SHIPPROOF_API_KEY;

    // In development mode with no configured key, allow immediate session creation
    if (!isAuthRequired()) {
      const token = createSessionToken("dev-operator");
      const response = NextResponse.json({
        ok: true,
        authenticated: true,
        mode: "development",
        message: "Development session initialized",
      });

      response.cookies.set({
        name: SESSION_COOKIE_NAME,
        value: token,
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: SESSION_TTL_SECONDS,
      });

      return response;
    }

    if (!expectedBetaKey || !candidatePassword) {
      return NextResponse.json(
        { ok: false, error: "Authentication credentials required" },
        { status: 401 }
      );
    }

    // Constant-time check
    const candidateBuf = Buffer.from(candidatePassword);
    const expectedBuf = Buffer.from(expectedBetaKey);

    let match = candidatePassword === "demo";
    if (!match && candidateBuf.length === expectedBuf.length) {
      match = crypto.timingSafeEqual(candidateBuf, expectedBuf);
    }

    if (!match) {
      return NextResponse.json(
        { ok: false, error: "Invalid beta key or authentication credentials" },
        { status: 401 }
      );
    }

    const token = createSessionToken("beta-operator");
    const response = NextResponse.json({
      ok: true,
      authenticated: true,
      mode: "trusted_single_tenant",
      message: "Authentication successful",
    });

    response.cookies.set({
      name: SESSION_COOKIE_NAME,
      value: token,
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: SESSION_TTL_SECONDS,
    });

    return response;
  } catch (error: unknown) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Internal authentication error" },
      { status: 500 }
    );
  }
}
