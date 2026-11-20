import { cookies } from "next/headers";
import crypto from "crypto";

const SESSION_COOKIE_NAME = "shipproof_session";
const SESSION_TTL_SECONDS = 86400; // 24 hours

function getSessionSecret(): string {
  return (
    process.env.SESSION_SECRET ||
    process.env.SHIPPROOF_BACKEND_API_KEY ||
    process.env.SHIPPROOF_API_KEY ||
    "shipproof_dev_session_secret_do_not_use_in_prod_12345678"
  );
}

export function isAuthRequired(): boolean {
  // If explicitly configured, or in non-development environment with an API key
  const hasKey = Boolean(
    process.env.SHIPPROOF_BETA_KEY ||
    process.env.SHIPPROOF_BACKEND_API_KEY ||
    process.env.SHIPPROOF_API_KEY
  );
  return hasKey;
}

export function getBackendApiKey(): string {
  return (
    process.env.SHIPPROOF_BACKEND_API_KEY ||
    process.env.SHIPPROOF_API_KEY ||
    ""
  );
}

export function createSessionToken(username: string = "beta-user"): string {
  const secret = getSessionSecret();
  const payload = {
    sub: username,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS,
    nonce: crypto.randomBytes(8).toString("hex"),
  };
  const payloadB64 = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = crypto.createHmac("sha256", secret).update(payloadB64).digest("hex");
  return `${payloadB64}.${sig}`;
}

export function verifySessionToken(tokenString?: string | null): { valid: boolean; user?: string } {
  if (!tokenString) return { valid: false };

  try {
    const parts = tokenString.split(".");
    if (parts.length !== 2) return { valid: false };

    const [payloadB64, sig] = parts;
    const secret = getSessionSecret();
    const expectedSig = crypto.createHmac("sha256", secret).update(payloadB64).digest("hex");

    // Constant-time comparison
    if (!crypto.timingSafeEqual(Buffer.from(sig, "hex"), Buffer.from(expectedSig, "hex"))) {
      return { valid: false };
    }

    const payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp < now) {
      return { valid: false };
    }

    return { valid: true, user: payload.sub };
  } catch {
    return { valid: false };
  }
}

export async function getSessionCookie(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE_NAME)?.value;
}

export { SESSION_COOKIE_NAME, SESSION_TTL_SECONDS };
