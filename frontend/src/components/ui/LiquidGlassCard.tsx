'use client';

import React, { useRef, useState } from 'react';

export interface LiquidGlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  glowColor?: string;
  intensity?: number;
  interactive?: boolean;
}

export function LiquidGlassCard({
  children,
  className = '',
  glowColor = 'rgba(255, 255, 255, 0.12)',
  intensity = 0.5,
  interactive = true,
  style,
  ...rest
}: LiquidGlassCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number; active: boolean }>({
    x: 0,
    y: 0,
    active: false,
  });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!interactive || !cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      active: true,
    });
  };

  const handleMouseLeave = () => {
    setMousePos((prev) => ({ ...prev, active: false }));
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className={`liquid-glass-card relative overflow-hidden rounded-[26px] transition-all duration-300 ${className}`}
      style={{
        ...style,
      }}
      {...rest}
    >
      {/* Liquid Glass Highlight Rim (User's .glassContainer::before) */}
      <div
        className="pointer-events-none absolute inset-0 rounded-[26px] z-0"
        style={{
          boxShadow:
            'inset 2px 2px 0px -2px rgba(255, 255, 255, 0.7), inset 0 0 3px 1px rgba(255, 255, 255, 0.4)',
        }}
      />

      {/* Liquid Glass Backdrop & Refraction (User's .glassContainer::after) */}
      <div
        className="pointer-events-none absolute inset-0 -z-10 rounded-[26px] bg-black/45 backdrop-blur-2xl"
        style={{
          filter: 'url(#container-glass)',
          WebkitBackdropFilter: 'blur(20px)',
          isolation: 'isolate',
        }}
      />

      {/* Interactive Cursor Spotlight Glow */}
      {interactive && mousePos.active && (
        <div
          className="pointer-events-none absolute -inset-px -z-10 transition-opacity duration-300"
          style={{
            background: `radial-gradient(400px circle at ${mousePos.x}px ${mousePos.y}px, ${glowColor}, transparent 70%)`,
            opacity: intensity,
          }}
        />
      )}

      {/* Content Layer — Preserves 100% text color, crisp typography, and full interactive visibility */}
      <div className="relative z-10 w-full h-full text-zinc-100">
        {children}
      </div>
    </div>
  );
}

export default LiquidGlassCard;
