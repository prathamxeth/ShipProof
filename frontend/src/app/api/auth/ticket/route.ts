import { NextResponse } from "next/server";
import {
  getSessionCookie,
  verifySessionToken,
  isAuthRequired,
  getBackendApiKey,
} from "@/lib/serverAuth";

export async function GET(request: Request) {
  try {
    const cookie = await getSessionCookie();
    const { valid } = verifySessionToken(cookie);
    const required = isAuthRequired();

    if (required && !valid) {
      return NextResponse.json(
        { error: "Authentication required to request scoped tickets" },
        { status: 401 }
      );
    }

    const { searchParams } = new URL(request.url);
    const scope = searchParams.get("scope") || "stream";
    const runId = searchParams.get("run_id");

    const backendUrl =
      process.env.INTERNAL_BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://127.0.0.1:8000";

    const backendKey = getBackendApiKey();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (backendKey) {
      headers["Authorization"] = `Bearer ${backendKey}`;
    }

    const backendResp = await fetch(`${backendUrl}/api/auth/ticket`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        scope,
        run_id: runId || undefined,
        ttl_seconds: 300,
      }),
      cache: "no-store",
    });

    if (!backendResp.ok) {
      const err = await backendResp.json().catch(() => ({}));
      return NextResponse.json(
        { error: err.detail || "Failed to acquire scoped ticket from backend" },
        { status: backendResp.status }
      );
    }

    const data = await backendResp.json();
    return NextResponse.json(data);
  } catch (error: unknown) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal ticket issuance error" },
      { status: 500 }
    );
  }
}
