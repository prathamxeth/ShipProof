"use client";

import React from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Clock,
  RotateCcw,
  Globe,
  ShoppingCart,
  Layers,
  CreditCard,
  ShieldCheck,
  PackageCheck,
  ChevronRight,
} from "lucide-react";
import LiquidGlassButton from "@/components/ui/LiquidGlassButton";

export type StepState = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "TIMED_OUT";

export interface ShopperStep {
  id: number;
  title: string;
  sublabel: string;
  target: string;
  state: StepState;
  duration?: string;
  error?: string;
}

export interface ShopperJourneyTimelineProps {
  steps: ShopperStep[];
  progressPercent: number;
  completedCount: number;
  totalCount: number;
  elapsedSec: number;
  currentUrl: string;
  runStatus: "running" | "passed" | "failed" | "error" | "queued" | "incomplete" | "cancelled" | "verified" | "timed_out";
  failureReason?: string | null;
  onRetry?: () => void;
  isStale?: boolean;
}

export function ShopperJourneyTimeline({
  steps,
  progressPercent,
  completedCount,
  totalCount = 7,
  elapsedSec = 0,
  currentUrl,
  runStatus,
  failureReason,
  onRetry,
  isStale = false,
}: ShopperJourneyTimelineProps) {
  const isRunning = runStatus === "running" || runStatus === "queued";
  const isPassed = runStatus === "passed" || runStatus === "verified";
  const isFailed = runStatus === "failed" || runStatus === "error" || runStatus === "incomplete" || runStatus === "timed_out" || isStale;

  // Step Icon mapping
  const getStepIcon = (id: number) => {
    switch (id) {
      case 1:
        return <Globe className="w-3.5 h-3.5" />;
      case 2:
        return <Layers className="w-3.5 h-3.5" />;
      case 3:
        return <Layers className="w-3.5 h-3.5" />;
      case 4:
        return <ShoppingCart className="w-3.5 h-3.5" />;
      case 5:
        return <CheckCircle2 className="w-3.5 h-3.5" />;
      case 6:
        return <CreditCard className="w-3.5 h-3.5" />;
      case 7:
        return <PackageCheck className="w-3.5 h-3.5" />;
      default:
        return <ShieldCheck className="w-3.5 h-3.5" />;
    }
  };

  return (
    <div className="w-full flex flex-col gap-3.5 p-4 rounded-2xl liquid-glass-panel">
      {/* 1. Header with Progress, Real Percentage & Elapsed Timer */}
      <div className="flex flex-col gap-2 border-b border-white/10 pb-3">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white tracking-tight flex items-center gap-1.5">
              <span>Customer Journey Progress</span>
              <span className="text-[10px] text-zinc-400 font-normal">
                ({completedCount} of {totalCount} verified)
              </span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Live Elapsed Time */}
            <div className="flex items-center gap-1 text-[11px] font-mono text-zinc-300">
              <Clock className="w-3 h-3 text-sky-400" />
              <span>{elapsedSec.toFixed(1)}s</span>
            </div>

            {/* Percentage Badge — Empty Liquid Glass */}
            <span
              className={`text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full border border-white/20 bg-transparent ${
                isPassed
                  ? "text-emerald-300"
                  : isFailed
                  ? "text-rose-300"
                  : "text-sky-300"
              }`}
            >
              {progressPercent}%
            </span>
          </div>
        </div>

        {/* Real Progress Bar — Liquid Glass Track */}
        <div className="w-full h-2 rounded-full bg-white/[0.04] border border-white/12 overflow-hidden relative shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)]">
          <div
            className={`h-full transition-all duration-300 ease-out rounded-full ${
              isPassed
                ? "bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.8)]"
                : isFailed
                ? "bg-gradient-to-r from-rose-500 via-rose-400 to-amber-400 shadow-[0_0_12px_rgba(244,63,94,0.6)]"
                : "bg-gradient-to-r from-sky-400 via-blue-400 to-sky-300 shadow-[0_0_12px_rgba(56,189,248,0.8)] animate-pulse"
            }`}
            style={{ width: `${Math.max(progressPercent, 4)}%` }}
          />
        </div>
      </div>

      {/* 2. Concise 7-Step Sequence List with Strict States */}
      <div className="grid grid-cols-1 gap-1.5">
        {steps.map((s) => {
          const isCurrentRunning = s.state === "RUNNING";
          const isDone = s.state === "COMPLETED";
          const isStepFailed = s.state === "FAILED" || s.state === "TIMED_OUT";

          return (
            <div
              key={s.id}
              className={`flex items-center justify-between p-2 rounded-xl border transition-all text-xs ${
                isCurrentRunning
                  ? "bg-white/[0.06] border-white/20 shadow-sm"
                  : isDone
                  ? "bg-white/[0.03] border-white/10"
                  : isStepFailed
                  ? "bg-white/[0.06] border-white/20 shadow-sm"
                  : "bg-transparent border-transparent opacity-50"
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                {/* State Indicator Glyph */}
                <div className="flex-none">
                  {isDone ? (
                    <div className="w-4 h-4 rounded-full bg-white/[0.08] border border-white/20 flex items-center justify-center text-emerald-400 shadow-sm">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    </div>
                  ) : isCurrentRunning ? (
                    <div className="w-4 h-4 rounded-full border-2 border-sky-400/30 border-t-sky-400 animate-spin" />
                  ) : isStepFailed ? (
                    <div className="w-4 h-4 rounded-full bg-white/[0.08] border border-white/20 flex items-center justify-center text-rose-400 shadow-sm">
                      <AlertTriangle className="w-3.5 h-3.5" />
                    </div>
                  ) : (
                    <div className="w-4 h-4 rounded-full border border-white/20 flex items-center justify-center text-[10px] font-mono text-zinc-400">
                      {s.id}
                    </div>
                  )}
                </div>

                {/* Step Title & Sublabel */}
                <div className="min-w-0 flex items-baseline gap-2 truncate">
                  <span
                    className={`font-medium truncate ${
                      isDone
                        ? "text-zinc-200"
                        : isCurrentRunning
                        ? "text-white font-semibold"
                        : isStepFailed
                        ? "text-rose-200 font-semibold"
                        : "text-zinc-400"
                    }`}
                  >
                    {s.title}
                  </span>
                  <span className="text-[10.5px] text-zinc-400 truncate hidden sm:inline">
                    {s.sublabel}
                  </span>
                </div>
              </div>

              {/* Status Pill & Target — Empty Liquid Glass */}
              <div className="flex items-center gap-2 flex-none ml-2">
                <span
                  className={`text-[10px] font-mono font-medium px-2 py-0.5 rounded-full border border-white/20 bg-transparent ${
                    isDone
                      ? "text-zinc-300"
                      : isCurrentRunning
                      ? "text-sky-200 animate-pulse"
                      : isStepFailed
                      ? "text-rose-200"
                      : "text-zinc-400"
                  }`}
                >
                  {s.state === "COMPLETED"
                    ? s.duration || "Verified"
                    : s.state === "RUNNING"
                    ? "In Progress..."
                    : s.state === "FAILED"
                    ? "Failed"
                    : s.state === "TIMED_OUT"
                    ? "Timed Out"
                    : "Pending"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. Stale Session Watchdog Alert */}
      {isStale && (
        <div className="w-full p-3 rounded-xl liquid-glass-subcard border-amber-400/40 flex items-center justify-between text-xs text-amber-200 shadow-md">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-none" />
            <span>Worker session reached 90s timeout. Test halted to prevent hanging.</span>
          </div>
          {onRetry && (
            <LiquidGlassButton variant="primary" size="sm" onClick={onRetry} className="flex-none ml-2">
              <RotateCcw className="w-3 h-3 mr-1" />
              Retry Test
            </LiquidGlassButton>
          )}
        </div>
      )}

      {/* 4. Failure Detail Callout */}
      {isFailed && failureReason && !isStale && (
        <div className="w-full p-3 rounded-xl liquid-glass-subcard border-rose-400/35 text-xs text-rose-200 flex items-center justify-between shadow-md">
          <div className="flex items-center gap-2 min-w-0">
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-none" />
            <span className="truncate">
              Obstruction: {failureReason.split("\n")[0]}
            </span>
          </div>
          {onRetry && (
            <LiquidGlassButton
              variant="glass"
              size="sm"
              onClick={onRetry}
              className="flex-none ml-2"
            >
              Retry Journey
            </LiquidGlassButton>
          )}
        </div>
      )}
    </div>
  );
}

export default ShopperJourneyTimeline;
