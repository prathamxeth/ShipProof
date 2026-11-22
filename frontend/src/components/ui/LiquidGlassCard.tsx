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
  glowColor = 'rgba(45, 74, 62, 0.08)',
  intensity = 0.4,
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
    <div className="liquid-card-wrap relative w-full h-full">
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className={`liquid-glass-card relative overflow-hidden rounded-[26px] ${className}`}
        style={{
          transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
          ...style,
        }}
        {...rest}
      >
        {/* Specular Liquid Rim Highlight (Springlight Alabaster Spec) */}
        <div
          className="pointer-events-none absolute inset-0 rounded-[26px] z-0"
          style={{
            boxShadow:
              'inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.95), inset 0 -1.5px 2px 0 rgba(45, 74, 62, 0.04)',
          }}
        />

        {/* Optical Refraction & Glass Displacement Backdrop */}
        <div
          className="pointer-events-none absolute inset-0 -z-10 rounded-[26px]"
          style={{
            background:
              'linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(255, 255, 255, 0.78))',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            filter: 'url(#container-glass)',
            isolation: 'isolate',
          }}
        />

        {/* Cursor Ambient Specular Highlight */}
        {interactive && mousePos.active && (
          <div
            className="pointer-events-none absolute -inset-px -z-10 transition-opacity duration-300"
            style={{
              background: `radial-gradient(400px circle at ${mousePos.x}px ${mousePos.y}px, ${glowColor}, transparent 70%)`,
              opacity: intensity,
            }}
          />
        )}

        {/* Content Layer — High-Contrast Visibility in Springlight */}
        <div className="relative z-10 w-full h-full text-[#1c2a22]">
          {children}
        </div>
      </div>

      {/* Underlying Liquid Ambient Shadow */}
      <div
        className="liquid-button-shadow"
        aria-hidden="true"
        style={{ borderRadius: '26px' }}
      />
    </div>
  );
}

export default LiquidGlassCard;
