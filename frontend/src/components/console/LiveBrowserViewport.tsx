"use client";

import React, { useState, useEffect } from "react";
import {
  ExternalLink,
  RotateCcw,
  Lock,
  Camera,
  Globe,
} from "lucide-react";

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
  runId,
}: LiveBrowserViewportProps) {
  const [viewMode, setViewMode] = useState<"live" | "screenshot">("live");
  const [iframeKey, setIframeKey] = useState(0);
  const [imageLoaded, setImageLoaded] = useState(false);

  // Default to screenshot view when a completed run has evidence screenshots
  useEffect(() => {
    if (screenshotUrl && (runStatus === "failed" || runStatus === "passed" || runStatus === "verified" || runStatus === "timed_out")) {
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

  return (
    <div className="w-full flex flex-col rounded-2xl overflow-hidden border border-[#2d4a3e]/15 bg-transparent shadow-none browser-preview-clean">
      {/* 1. Browser Chrome Header Bar — Clean Transparent */}
      <div className="flex items-center justify-between px-3.5 py-2 border-b border-[#2d4a3e]/12 bg-white/40 backdrop-blur-md gap-3">
        {/* macOS Traffic Lights */}
        <div className="flex items-center gap-1.5 flex-none">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-[0_0_4px_rgba(244,63,94,0.4)]" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500 shadow-[0_0_4px_rgba(245,158,11,0.4)]" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_4px_rgba(16,185,129,0.4)]" />
        </div>

        {/* Reload button */}
        <button
          type="button"
          onClick={handleRefresh}
          title="Reload browser view"
          className="p-1 rounded-lg hover:bg-black/5 text-[#2d4a3e] hover:text-[#1c2a22] transition-colors cursor-pointer flex-none"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${isLiveRunning ? "animate-spin" : ""}`} />
        </button>

        {/* URL Address Omnibar — Clean Realistic Browser Address */}
        <div className="flex-1 min-w-0 max-w-xl mx-auto flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/80 border border-[#2d4a3e]/15 text-[11px] font-mono text-[#1c2a22] shadow-[0_1px_3px_rgba(35,55,45,0.04)]">
          <Lock className="w-3 h-3 text-[#1b7a4b] flex-none" />
          <span className="text-[#4e6357] select-none">http://</span>
          <span className="text-[#1c2a22] font-semibold truncate">
            {currentUrl.replace(/^https?:\/\//, "")}
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 flex-none">
          {/* Mode Switcher if screenshot is available */}
          {screenshotUrl && (
            <div className="flex items-center bg-white/60 p-0.5 rounded-lg border border-[#2d4a3e]/15 text-[10px]">
              <button
                type="button"
                onClick={() => setViewMode("live")}
                className={`px-2 py-1 rounded-md transition-all font-semibold cursor-pointer ${
                  viewMode === "live"
                    ? "bg-white text-[#1c2a22] shadow-sm border border-[#2d4a3e]/15"
                    : "text-[#4e6357] hover:text-[#1c2a22]"
                }`}
              >
                <Globe className="w-3 h-3 inline mr-1" />
                Live Store
              </button>
              <button
                type="button"
                onClick={() => setViewMode("screenshot")}
                className={`px-2 py-1 rounded-md transition-all font-semibold cursor-pointer ${
                  viewMode === "screenshot"
                    ? "bg-white text-[#1c2a22] shadow-sm border border-[#2d4a3e]/15"
                    : "text-[#4e6357] hover:text-[#1c2a22]"
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
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/70 hover:bg-white/95 border border-[#2d4a3e]/15 text-[10.5px] font-sans font-semibold text-[#2d4a3e] hover:text-[#1c2a22] transition-all cursor-pointer shadow-[0_1px_2px_rgba(35,55,45,0.04)]"
          >
            <span>Open Tab</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* 2. Full-Size Landscape 16:9 Viewport Area — Zero Overlay Occlusion */}
      <div className="relative w-full aspect-[16/9] min-h-[380px] bg-transparent overflow-hidden flex items-center justify-center">
        {viewMode === "screenshot" && screenshotUrl ? (
          <div className="relative w-full h-full flex items-center justify-center bg-transparent p-0">
            {!imageLoaded && (
              <div className="absolute inset-0 flex items-center justify-center bg-transparent z-10 text-xs text-[#4e6357] font-semibold">
                <div className="w-4 h-4 border-2 border-[#2d4a3e]/20 border-t-[#2d4a3e] rounded-full animate-spin mr-2" />
                Loading Chromium Evidence Capture...
              </div>
            )}
            {/* Real Chromium Screenshot Artifact — Full width & height, landscape 16:9, contain proportions */}
            <img
              src={screenshotUrl}
              alt="Kane CLI Chromium Agent Capture"
              onLoad={() => setImageLoaded(true)}
              className="w-full h-full object-contain transition-opacity duration-300"
              style={{ opacity: imageLoaded ? 1 : 0 }}
            />
          </div>
        ) : (
          <div className="relative w-full h-full bg-transparent">
            {/* Live Interactive Storefront Viewport */}
            <iframe
              key={iframeKey}
              src={currentUrl}
              title="ShipProof Acme Voyager Storefront"
              className="w-full h-full border-none bg-transparent"
              sandbox="allow-same-origin allow-scripts allow-forms"
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default LiveBrowserViewport;
