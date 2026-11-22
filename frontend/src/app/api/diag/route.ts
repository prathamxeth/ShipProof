import { NextResponse } from "next/server";
import fs from "fs";

export async function GET() {
  const results: Record<string, unknown> = {
    timestamp: new Date().toISOString(),
    node_env: process.env.NODE_ENV,
    port: process.env.PORT,
    backend_url: process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000",
  };

  // Test backend connectivity
  try {
    const res = await fetch("http://127.0.0.1:8000/api/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    results.backend_health = {
      status: res.status,
      ok: res.ok,
      data: await res.json().catch(() => null),
    };
  } catch (err: unknown) {
    results.backend_health = {
      error: err instanceof Error ? err.message : String(err),
    };
  }

  // Test store connectivity
  try {
    const res = await fetch("http://127.0.0.1:3005/", {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    results.store_health = {
      status: res.status,
      ok: res.ok,
    };
  } catch (err: unknown) {
    results.store_health = {
      error: err instanceof Error ? err.message : String(err),
    };
  }

  // Read backend logs if present
  try {
    if (fs.existsSync("/tmp/backend.log")) {
      const log = fs.readFileSync("/tmp/backend.log", "utf-8");
      results.backend_log_tail = log.slice(-2000);
    }
  } catch {
    results.backend_log_tail = "Could not read /tmp/backend.log";
  }

  return NextResponse.json(results);
}
