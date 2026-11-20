'use client';

import React from 'react';

export interface LiquidGlassButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  variant?: 'primary' | 'glass' | 'danger' | 'emerald';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  sublabel?: React.ReactNode;
  isActionTile?: boolean;
}

export const LiquidGlassButton = React.forwardRef<
  HTMLButtonElement,
  LiquidGlassButtonProps
>(
  (
    {
      children,
      variant = 'primary',
      size = 'md',
      fullWidth = false,
      icon,
      badge,
      sublabel,
      isActionTile = false,
      className = '',
      disabled,
      ...props
    },
    ref
  ) => {
    // Sizing scales
    const sizeClasses = {
      sm: 'text-[11px] py-1.5 px-3 min-h-[32px]',
      md: 'text-xs py-2 px-4 min-h-[40px]',
      lg: 'text-sm py-2.5 px-5 min-h-[46px]',
    }[size];

    // Variant colors for glow, text, and badge
    const variantConfig = {
      primary: {
        text: 'text-white',
        border: 'border-blue-400/30',
        bg: 'bg-gradient-to-r from-blue-600/30 via-blue-500/20 to-blue-600/30',
        badgeBg: 'bg-blue-500/25 text-blue-200 border-blue-400/40',
        shadow: 'shadow-blue-500/20',
      },
      glass: {
        text: 'text-zinc-100',
        border: 'border-white/15',
        bg: 'bg-gradient-to-r from-white/[0.08] via-white/[0.14] to-white/[0.08]',
        badgeBg: 'bg-white/[0.1] text-zinc-200 border-white/20',
        shadow: 'shadow-white/5',
      },
      danger: {
        text: 'text-rose-100',
        border: 'border-rose-400/30',
        bg: 'bg-gradient-to-r from-rose-600/30 via-rose-500/20 to-rose-600/30',
        badgeBg: 'bg-rose-500/25 text-rose-200 border-rose-400/40',
        shadow: 'shadow-rose-500/20',
      },
      emerald: {
        text: 'text-emerald-100',
        border: 'border-emerald-400/30',
        bg: 'bg-gradient-to-r from-emerald-600/30 via-emerald-500/20 to-emerald-600/30',
        badgeBg: 'bg-emerald-500/25 text-emerald-200 border-emerald-400/40',
        shadow: 'shadow-emerald-500/20',
      },
    }[variant];

    return (
      <div
        className={`liquid-button-wrap inline-block relative ${
          fullWidth ? 'w-full' : ''
        } ${disabled ? 'opacity-40 pointer-events-none' : ''}`}
      >
        <button
          ref={ref}
          disabled={disabled}
          className={`liquid-glass-btn relative box-border flex min-w-0 items-center justify-center font-medium font-sans cursor-pointer select-none ${
            isActionTile ? 'rounded-2xl' : 'rounded-full'
          } ${sizeClasses} ${variantConfig.text} ${variantConfig.bg} ${
            fullWidth ? 'w-full' : ''
          } ${className}`}
          style={{
            transition:
              'background-color 0.2s ease, transform 0.2s cubic-bezier(0.25, 1, 0.5, 1), box-shadow 0.2s ease, filter 0.2s ease',
          }}
          {...props}
        >
          {/* Badge or Icon Disc (as in Stepper action tile) */}
          {(badge || icon) && (
            <span
              className={`grid h-[24px] w-[24px] flex-none place-items-center rounded-full text-[11.5px] leading-none font-semibold tabular-nums border ${variantConfig.badgeBg} transition-all duration-200 mr-2`}
              style={{
                boxShadow: 'inset 0 1px 1px rgba(255, 255, 255, 0.4)',
              }}
            >
              {badge || icon}
            </span>
          )}

          {/* Label & Sublabel */}
          <span className="flex min-w-0 flex-col text-left">
            <span className="overflow-hidden text-ellipsis whitespace-nowrap leading-tight tracking-tight flex items-center gap-1.5 font-semibold">
              {children}
            </span>
            {sublabel && (
              <span className="text-[10px] text-zinc-400 font-normal leading-none mt-0.5">
                {sublabel}
              </span>
            )}
          </span>
        </button>

        {/* Soft Ambient Shadow */}
        <div className="liquid-button-shadow" aria-hidden="true" />
      </div>
    );
  }
);

LiquidGlassButton.displayName = 'LiquidGlassButton';

export default LiquidGlassButton;
