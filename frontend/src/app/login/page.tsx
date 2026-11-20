"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import LiquidGlassCard from "@/components/ui/LiquidGlassCard";
import LiquidGlassButton from "@/components/ui/LiquidGlassButton";
import { Cpu, Key, ArrowRight, ShieldCheck, AlertCircle } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError("Please enter your ShipProof beta key.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ password: password.trim() }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(data.error || data.detail || "Authentication failed: invalid credentials.");
        setLoading(false);
        return;
      }

      const destination = searchParams.get("from") || "/";
      router.push(destination);
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Network error.");
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center p-4 text-zinc-100 overflow-hidden">
      <div className="relative z-10 w-full max-w-md">
        <LiquidGlassCard
          glowColor="rgba(24, 99, 220, 0.4)"
          className="p-8 flex flex-col gap-6 shadow-2xl"
        >
          {/* Header */}
          <div className="flex flex-col gap-2 items-center text-center">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-[#1863dc] via-[#2563eb] to-[#38bdf8] flex items-center justify-center shadow-lg shadow-blue-500/20 mb-2">
              <Cpu className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-white">ShipProof Demo</h1>
            <p className="text-xs text-zinc-300">
              24/7 AI Customer Simulation &amp; Self-Healing Store Guardian
            </p>
          </div>

          {/* Status Badge */}
          <div className="flex items-center justify-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.04] border border-white/10 text-xs font-sans text-zinc-300">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Interactive Demo Ready for Evaluation</span>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
              <AlertCircle className="w-4 h-4 text-rose-400 flex-none" />
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-zinc-300">
                Demo Passcode
              </label>
              <div className="relative flex items-center">
                <Key className="w-4 h-4 text-zinc-500 absolute left-3 pointer-events-none" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  placeholder="Enter passcode (e.g. demo)..."
                  className="w-full bg-black/50 border border-white/10 rounded-xl pl-9 pr-3 py-2.5 text-xs text-zinc-200 placeholder:text-zinc-500 focus:border-blue-500/50 focus:outline-none transition-colors"
                  autoFocus
                />
              </div>
            </div>

            <LiquidGlassButton
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              isActionTile
              icon={<ArrowRight className="w-3.5 h-3.5" />}
              sublabel="Test 24/7 autonomous store protection & auto-healing"
              disabled={loading || !password.trim()}
            >
              {loading ? "Opening Interactive Demo..." : "Enter Interactive Demo"}
            </LiquidGlassButton>
          </form>

          <div className="text-center text-[11px] text-zinc-400">
            ShipProof • Protecting Online Store Revenue 24/7
          </div>
        </LiquidGlassCard>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen w-full text-zinc-400 flex items-center justify-center font-mono text-xs">
          Loading access gateway...
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
