"use client";

import React from "react";
import HoloMosaic from "./HoloMosaic";

export function HoloBackground() {
  return (
    <div
      className="fixed inset-0 z-0 overflow-hidden pointer-events-auto"
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw",
        height: "100vh",
        zIndex: 0,
        backgroundColor: "#100e17",
      }}
    >
      <HoloMosaic
        color="#100e17"
        metalColor="#e8ebf1"
        spectrum="full"
        tileSize={1.1}
        gap={0.08}
        scatter={0.32}
        tilt={0.38}
        saturation={0.38}
        intensity={1.35}
        ripple={0.65}
        glitter={0.9}
        sheen={0.85}
        grain={0.08}
        speed={0.45}
        intro={true}
        mouseInteraction={true}
        mouseStrength={1.2}
        mouseRadius={0.32}
        flipOnClick={true}
        style={{ width: "100%", height: "100%" }}
      />
      {/* Translucent vignette so cards pop while the holographic mosaic tiles shimmer behind */}
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#090a0f]/30 via-transparent to-[#090a0f]/50"
        aria-hidden="true"
        style={{ pointerEvents: "none" }}
      />
    </div>
  );
}

export default HoloBackground;
