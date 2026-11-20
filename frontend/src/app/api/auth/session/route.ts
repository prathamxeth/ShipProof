import { NextResponse } from "next/server";
import {
  getSessionCookie,
  verifySessionToken,
  isAuthRequired,
} from "@/lib/serverAuth";

export async function GET() {
  const cookie = await getSessionCookie();
  const { valid, user } = verifySessionToken(cookie);
  const required = isAuthRequired();

  return NextResponse.json({
    authenticated: valid || !required,
    mode: required ? "trusted_single_tenant" : "development",
    user: valid ? user : (!required ? "dev-local-user" : null),
    requiresAuth: required,
  });
}
