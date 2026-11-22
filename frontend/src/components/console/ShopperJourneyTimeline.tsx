"use client";

import React from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Clock,
  RotateCcw,
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
  currentUrl?: string;
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
  runStatus,
  failureReason,
  onRetry,
  isStale = false,
}: ShopperJourneyTimelineProps) {
  const isPassed = runStatus === "passed" || runStatus === "verified";
  const isFailed = !isPassed && (runStatus === "failed" || runStatus === "error" || runStatus === "incomplete" || runStatus === "timed_out" || isStale);

  return (
    <div className="w-full flex flex-col gap-3.5 p-4 rounded-2xl bg-transparent border border-[#2d4a3e]/15 shadow-none">
      {/* 1. Header with Progress, Real Percentage & Elapsed Timer */}
      <div className="flex flex-col gap-2 border-b border-[#2d4a3e]/10 pb-3">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-[#1c2a22] tracking-tight flex items-center gap-1.5">
              <span>Customer Journey Progress</span>
              <span className="text-[10px] text-[#4e6357] font-medium">
                ({completedCount} of {totalCount} verified)
              </span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Live Elapsed Time */}
            <div className="flex items-center gap-1 text-[11px] font-mono text-[#1c2a22] font-semibold">
              <Clock className="w-3 h-3 text-[#2d4a3e]" />
              <span>{elapsedSec.toFixed(1)}s</span>
            </div>

            {/* Percentage Badge */}
            <span
              className={`text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full border ${
                isPassed
                  ? "text-emerald-800 bg-emerald-50 border-emerald-200"
                  : isFailed
                  ? "text-rose-800 bg-rose-50 border-rose-200"
                  : "text-sky-800 bg-sky-50 border-sky-200"
              }`}
            >
              {progressPercent}%
            </span>
          </div>
        </div>

        {/* Real Progress Bar */}
        <div className="w-full h-2 rounded-full bg-black/5 border border-[#2d4a3e]/15 overflow-hidden relative shadow-none">
          <div
            className={`h-full transition-all duration-300 ease-out rounded-full ${
              isPassed
                ? "bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-500 shadow-[0_0_8px_rgba(27,122,75,0.4)]"
                : isFailed
                ? "bg-gradient-to-r from-rose-600 via-rose-500 to-amber-500 shadow-[0_0_8px_rgba(217,56,58,0.4)]"
                : "bg-gradient-to-r from-sky-600 via-blue-600 to-sky-500 shadow-[0_0_8px_rgba(14,116,144,0.4)] animate-pulse"
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
                  ? "bg-white/90 border-[#2d4a3e]/25 shadow-sm"
                  : isDone
                  ? "bg-white/75 border-[#2d4a3e]/12"
                  : isStepFailed
                  ? "bg-rose-50/90 border-rose-300 shadow-sm"
                  : "bg-white/40 border-transparent opacity-75"
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                {/* State Indicator Glyph */}
                <div className="flex-none">
                  {isDone ? (
                    <div className="w-4 h-4 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700 shadow-sm">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    </div>
                  ) : isCurrentRunning ? (
                    <div className="w-4 h-4 rounded-full border-2 border-sky-400/30 border-t-sky-600 animate-spin" />
                  ) : isStepFailed ? (
                    <div className="w-4 h-4 rounded-full bg-rose-100 border border-rose-300 flex items-center justify-center text-rose-700 shadow-sm">
                      <AlertTriangle className="w-3.5 h-3.5" />
                    </div>
                  ) : (
                    <div className="w-4 h-4 rounded-full border border-[#2d4a3e]/20 flex items-center justify-center text-[10px] font-mono text-[#4e6357] font-semibold bg-white/50">
                      {s.id}
                    </div>
                  )}
                </div>

                {/* Step Title & Sublabel */}
                <div className="min-w-0 flex items-baseline gap-2 truncate">
                  <span
                    className={`font-semibold truncate ${
                      isDone
                        ? "text-[#1c2a22]"
                        : isCurrentRunning
                        ? "text-[#1c2a22]"
                        : isStepFailed
                        ? "text-rose-900"
                        : "text-[#4e6357]"
                    }`}
                  >
                    {s.title}
                  </span>
                  <span className="text-[10.5px] text-[#4e6357] font-normal truncate hidden sm:inline">
                    {s.sublabel}
                  </span>
                </div>
              </div>

              {/* Status Pill & Target */}
              <div className="flex items-center gap-2 flex-none ml-2">
                <span
                  className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full border ${
                    isDone
                      ? "text-[#2d4a3e] bg-white/80 border-[#2d4a3e]/15"
                      : isCurrentRunning
                      ? "text-sky-700 bg-sky-50 border-sky-200 animate-pulse"
                      : isStepFailed
                      ? "text-rose-700 bg-rose-50 border-rose-200"
                      : "text-[#4e6357] bg-white/50 border-[#2d4a3e]/10"
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

      {/* 3. Authoritative Single Timeout / Failure Callout */}
      {!isPassed && (isStale || runStatus === "timed_out") ? (
        <div className="w-full p-3 rounded-xl bg-amber-50/90 border border-amber-300 flex items-center justify-between text-xs text-amber-900 shadow-sm">
          <div className="flex items-center gap-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-none" />
            <div className="flex flex-col min-w-0">
              <span className="font-bold text-amber-950">Execution Timed Out ({elapsedSec.toFixed(1)}s)</span>
              <span className="text-[11px] text-amber-900 truncate">
                {completedCount} of {totalCount} steps completed before worker session stopped.
              </span>
            </div>
          </div>
          {onRetry && (
            <LiquidGlassButton variant="primary" size="sm" onClick={onRetry} className="flex-none ml-2">
              <RotateCcw className="w-3 h-3 mr-1" />
              Retry Test
            </LiquidGlassButton>
          )}
        </div>
      ) : !isPassed && isFailed && failureReason ? (
        <div className="w-full p-3 rounded-xl bg-rose-50/90 border border-rose-300 text-xs text-rose-900 flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-rose-600 flex-none" />
            <div className="flex flex-col min-w-0">
              <span className="font-bold text-rose-950">Customer Journey Obstructed</span>
              <span className="text-[11px] text-rose-900 truncate">
                {failureReason.split("\n")[0]}
              </span>
            </div>
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
      ) : null}
    </div>
  );
}

export default ShopperJourneyTimeline;
