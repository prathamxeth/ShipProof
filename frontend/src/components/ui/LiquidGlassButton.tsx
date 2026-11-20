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
  loading?: boolean;
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
      loading = false,
      className = '',
      disabled,
      ...props
    },
    ref
  ) => {
    // Sizing scales (multiples of 4px)
    const sizeClasses = {
      sm: 'text-[11px] py-1.5 px-3 min-h-[32px]',
      md: 'text-xs py-2 px-4 min-h-[40px]',
      lg: 'text-sm py-2.5 px-5 min-h-[44px]',
    }[size];

    // Variant colors for glow, text, and badge
    const variantConfig = {
      primary: {
        text: 'text-white',
        border: 'border-blue-400/30',
        bg: 'bg-gradient-to-r from-blue-600/30 via-blue-500/20 to-blue-600/30',
        badgeBg: 'bg-blue-500/25 text-blue-200 border-blue-400/40',
        shadow: 'shadow-blue-500/20',
        focusRing: 'focus-visible:outline-sky-400 focus-visible:ring-sky-400/40',
      },
      glass: {
        text: 'text-zinc-100',
        border: 'border-white/15',
        bg: 'bg-gradient-to-r from-white/[0.08] via-white/[0.14] to-white/[0.08]',
        badgeBg: 'bg-white/[0.1] text-zinc-200 border-white/20',
        shadow: 'shadow-white/5',
        focusRing: 'focus-visible:outline-sky-400 focus-visible:ring-sky-400/40',
      },
      danger: {
        text: 'text-rose-100',
        border: 'border-rose-400/30',
        bg: 'bg-gradient-to-r from-rose-600/30 via-rose-500/20 to-rose-600/30',
        badgeBg: 'bg-rose-500/25 text-rose-200 border-rose-400/40',
        shadow: 'shadow-rose-500/20',
        focusRing: 'focus-visible:outline-rose-400 focus-visible:ring-rose-400/40',
      },
      emerald: {
        text: 'text-emerald-100',
        border: 'border-emerald-400/30',
        bg: 'bg-gradient-to-r from-emerald-600/30 via-emerald-500/20 to-emerald-600/30',
        badgeBg: 'bg-emerald-500/25 text-emerald-200 border-emerald-400/40',
        shadow: 'shadow-emerald-500/20',
        focusRing: 'focus-visible:outline-emerald-400 focus-visible:ring-emerald-400/40',
      },
    }[variant];

    const isDisabled = disabled || loading;

    return (
      <div
        className={`liquid-button-wrap inline-block relative ${
          fullWidth ? 'w-full' : ''
        } ${isDisabled ? 'opacity-45 pointer-events-none' : ''}`}
      >
        <button
          ref={ref}
          disabled={isDisabled}
          aria-busy={loading}
          className={`liquid-glass-btn relative box-border flex min-w-0 items-center justify-center font-medium font-sans select-none whitespace-nowrap focus-visible:outline-2 focus-visible:outline-offset-2 ${variantConfig.focusRing} disabled:cursor-not-allowed disabled:pointer-events-none disabled:shadow-none disabled:opacity-50 cursor-pointer ${
            isActionTile ? 'rounded-2xl' : 'rounded-full'
          } ${sizeClasses} ${variantConfig.text} ${variantConfig.bg} ${
            fullWidth ? 'w-full' : ''
          } ${className}`}
          style={{
            transition:
              'background-color 0.15s ease, transform 0.15s cubic-bezier(0.25, 1, 0.5, 1), box-shadow 0.15s ease, filter 0.15s ease',
          }}
          {...props}
        >
          {/* Loading Spinner */}
          {loading && (
            <svg
              className="animate-spin -ml-1 mr-2 h-3.5 w-3.5 text-current"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          )}

          {/* Badge or Icon Disc (as in Stepper action tile) */}
          {!loading && (badge || icon) && (
            <span
              className={`grid h-[24px] w-[24px] flex-none place-items-center rounded-full text-[11.5px] leading-none font-semibold tabular-nums border ${variantConfig.badgeBg} mr-2`}
              style={{
                boxShadow: 'inset 0 1px 1px rgba(255, 255, 255, 0.4)',
                transition: 'background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease',
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
              <span className="text-[10px] text-zinc-300 font-normal leading-none mt-0.5 whitespace-nowrap">
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
