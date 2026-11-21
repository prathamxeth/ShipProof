"use client";

import React, { useState, useEffect } from "react";
import {
  ExternalLink,
  RotateCcw,
  Lock,
  Camera,
  Globe,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import LiquidGlassButton from "@/components/ui/LiquidGlassButton";

export interface LiveBrowserViewportProps {
  currentUrl?: string;
  runStatus?: "running" | "passed" | "failed" | "error" | "queued" | "incomplete" | "cancelled" | "verified" | "timed_out";
  screenshotUrl?: string | null;
  activeStepTitle?: string;
  failureReason?: string | null;
  elapsedSec?: number;
  runId?: string;
  onRetry?: () => void;
}

export function LiveBrowserViewport({
  currentUrl = "http://127.0.0.1:3005",
  runStatus = "passed",
  screenshotUrl,
  activeStepTitle = "Storefront ready",
  failureReason,
  elapsedSec = 0,
  runId,
  onRetry,
}: LiveBrowserViewportProps) {
  const [viewMode, setViewMode] = useState<"live" | "screenshot">("live");
  const [iframeKey, setIframeKey] = useState(0);
  const [imageLoaded, setImageLoaded] = useState(false);

  // Default to screenshot view when a completed run has evidence screenshots
  useEffect(() => {
    if (screenshotUrl && (runStatus === "failed" || runStatus === "passed")) {
      setViewMode("screenshot");
      setImageLoaded(false);
    } else {
      setViewMode("live");
    }
  }, [screenshotUrl, runStatus, runId]);

  const handleRefresh = () => {
    setIframeKey((prev) => prev + 1);
  };

  const isLiveRunning = runStatus === "running" || runStatus === "queued";
  const isFailed = runStatus === "failed" || runStatus === "error" || runStatus === "incomplete" || runStatus === "timed_out";
  const isPassed = runStatus === "passed" || runStatus === "verified";

  return (
    <div className="w-full flex flex-col rounded-2xl overflow-hidden border border-white/20 bg-white/[0.04] backdrop-blur-2xl shadow-[inset_0_1.5px_1px_rgba(255,255,255,0.45),0_16px_36px_-12px_rgba(0,0,0,0.5)]">
      {/* 1. Browser Chrome Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-white/12 bg-white/[0.06] backdrop-blur-md gap-3">
        {/* macOS Traffic Lights */}
        <div className="flex items-center gap-1.5 flex-none">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80 shadow-[0_0_6px_rgba(244,63,94,0.6)]" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80 shadow-[0_0_6px_rgba(245,158,11,0.6)]" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 shadow-[0_0_6px_rgba(16,185,129,0.6)]" />
        </div>

        {/* Reload button */}
        <button
          type="button"
          onClick={handleRefresh}
          title="Reload browser view"
          className="p-1 rounded-lg hover:bg-white/10 text-zinc-300 hover:text-white transition-colors cursor-pointer flex-none"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${isLiveRunning ? "animate-spin" : ""}`} />
        </button>

        {/* URL Address Omnibar — Liquid Glass Pill */}
        <div className="flex-1 min-w-0 max-w-xl mx-auto flex items-center justify-between px-3 py-1 rounded-full bg-white/[0.04] border border-white/18 text-[11px] font-mono text-zinc-200 shadow-[inset_0_1px_1px_rgba(255,255,255,0.2)]">
          <div className="flex items-center gap-1.5 truncate">
            <Lock className="w-3 h-3 text-emerald-400 flex-none" />
            <span className="text-zinc-400 select-none">http://</span>
            <span className="text-white font-semibold truncate">
              {currentUrl.replace(/^https?:\/\//, "")}
            </span>
          </div>

          <span
            className={`text-[9.5px] uppercase font-sans font-semibold tracking-wider px-2 py-0.5 rounded-full border border-white/20 bg-transparent flex-none ml-2 ${
              isLiveRunning
                ? "text-sky-300 animate-pulse"
                : isFailed
                ? "text-rose-300"
                : "text-emerald-300"
            }`}
          >
            {isLiveRunning
              ? "● LIVE SHOPPER ACTIVE"
              : isFailed
              ? "✕ DEFECT FOUND"
              : "✓ VERIFIED SAFE"}
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 flex-none">
          {/* Mode Switcher if screenshot is available */}
          {screenshotUrl && (
            <div className="flex items-center bg-white/[0.06] p-0.5 rounded-lg border border-white/14 text-[10px] backdrop-blur-md">
              <button
                type="button"
                onClick={() => setViewMode("live")}
                className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                  viewMode === "live"
                    ? "bg-white/20 text-white shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Globe className="w-3 h-3 inline mr-1" />
                Live Store
              </button>
              <button
                type="button"
                onClick={() => setViewMode("screenshot")}
                className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                  viewMode === "screenshot"
                    ? "bg-white/20 text-white shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Camera className="w-3 h-3 inline mr-1" />
                Agent Evidence
              </button>
            </div>
          )}

          {/* Open Store directly in New Tab */}
          <a
            href={currentUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Open real target store in a separate browser tab"
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/[0.08] hover:bg-white/[0.15] border border-white/20 text-[10.5px] font-sans font-medium text-zinc-200 hover:text-white transition-all cursor-pointer"
          >
            <span>Open Tab</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* 2. Live Browser Viewport Body */}
      <div className="relative w-full h-[320px] bg-white/[0.02] overflow-hidden flex items-center justify-center">
        {viewMode === "screenshot" && screenshotUrl ? (
          <div className="relative w-full h-full flex flex-col items-center justify-center bg-white/[0.03] p-2">
            {!imageLoaded && (
              <div className="absolute inset-0 flex items-center justify-center bg-white/[0.05] backdrop-blur-md z-10 text-xs text-zinc-300">
                <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin mr-2" />
                Loading Chromium Evidence Capture...
              </div>
            )}
            {/* Real Chromium Screenshot Artifact */}
            <img
              src={screenshotUrl}
              alt="Kane CLI Chromium Agent Capture"
              onLoad={() => setImageLoaded(true)}
              className="max-h-full max-w-full object-contain rounded-lg border border-white/15 shadow-2xl transition-opacity duration-300"
              style={{ opacity: imageLoaded ? 1 : 0 }}
            />
            <div className="absolute top-4 left-4 px-2.5 py-1 rounded-full bg-white/[0.08] border border-white/20 backdrop-blur-xl text-[10.5px] text-zinc-200 font-mono flex items-center gap-1.5 shadow-md">
              <Camera className="w-3 h-3 text-sky-400" />
              <span>Kane CLI Chromium Screenshot • Test {runId?.slice(0, 8)}</span>
            </div>
          </div>
        ) : (
          <div className="relative w-full h-full">
            {/* Live Interactive Storefront Viewport */}
            <iframe
              key={iframeKey}
              src={currentUrl}
              title="ShipProof Acme Voyager Storefront"
              className="w-full h-full border-none bg-transparent"
              sandbox="allow-same-origin allow-scripts allow-forms"
            />

            {/* Specular glass reflection overlay */}
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/[0.04] via-transparent to-white/[0.02]" />
          </div>
        )}

        {/* Live Active Interaction Banner */}
        {isLiveRunning && (
          <div className="absolute bottom-3 left-3 right-3 p-2.5 rounded-xl liquid-glass-subcard border-sky-400/35 flex items-center justify-between text-xs shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-sky-400 animate-ping" />
              <span className="font-semibold text-white truncate">
                AI Shopper: {activeStepTitle}
              </span>
            </div>
            <span className="font-mono text-[11px] text-sky-300 flex-none ml-2">
              T+{elapsedSec.toFixed(1)}s
            </span>
          </div>
        )}

        {/* Failure Callout Banner when Defect Triggered */}
        {isFailed && failureReason && (
          <div className="absolute bottom-3 left-3 right-3 p-3 rounded-xl liquid-glass-subcard border-rose-400/35 flex items-center justify-between text-xs shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="w-4 h-4 text-rose-400 flex-none" />
              <div>
                <span className="font-bold text-rose-200 block">
                  Checkout Obstructed — Defect Verified in Chromium
                </span>
                <span className="text-[11px] text-zinc-300 leading-tight">
                  {failureReason.split("\n")[0]}
                </span>
              </div>
            </div>
            {onRetry && (
              <LiquidGlassButton
                variant="danger"
                size="sm"
                onClick={onRetry}
                className="flex-none ml-3"
              >
                Retry Test
              </LiquidGlassButton>
            )}
          </div>
        )}

        {/* Success Confirmation Banner */}
        {isPassed && (
          <div className="absolute bottom-3 left-3 right-3 p-2.5 rounded-xl liquid-glass-subcard border-emerald-400/35 flex items-center justify-between text-xs shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-none" />
              <span className="font-semibold text-emerald-100">
                Purchase Journey Completed: Customer placed order successfully with 0 errors.
              </span>
            </div>
            <span className="font-mono text-[10.5px] text-emerald-300 font-semibold px-2 py-0.5 rounded-full bg-white/[0.08] border border-white/20">
              100% HEALTHY
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default LiveBrowserViewport;
