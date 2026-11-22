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

    // Variant colors: Springlight refined translucent buttons
    const variantConfig = {
      primary: {
        text: 'text-[#1c2a22]',
        border: 'border-[#2d4a3e]/20',
        bg: 'bg-white/85',
        badgeBg: 'bg-[#2d4a3e]/10 text-[#2d4a3e] border-[#2d4a3e]/20',
        shadow: 'shadow-[0_2px_8px_rgba(35,55,45,0.06)]',
        focusRing: 'focus-visible:outline-[#2d4a3e] focus-visible:ring-[#2d4a3e]/30',
      },
      glass: {
        text: 'text-[#1c2a22]',
        border: 'border-[#2d4a3e]/15',
        bg: 'bg-white/75',
        badgeBg: 'bg-[#2d4a3e]/10 text-[#2d4a3e] border-[#2d4a3e]/20',
        shadow: 'shadow-[0_2px_8px_rgba(35,55,45,0.05)]',
        focusRing: 'focus-visible:outline-[#2d4a3e] focus-visible:ring-[#2d4a3e]/30',
      },
      danger: {
        text: 'text-[#d9383a]',
        border: 'border-[#d9383a]/30',
        bg: 'bg-[#d9383a]/10',
        badgeBg: 'bg-[#d9383a]/15 text-[#d9383a] border-[#d9383a]/30',
        shadow: 'shadow-[0_2px_8px_rgba(217,56,58,0.1)]',
        focusRing: 'focus-visible:outline-[#d9383a] focus-visible:ring-[#d9383a]/30',
      },
      emerald: {
        text: 'text-[#1b7a4b]',
        border: 'border-[#1b7a4b]/30',
        bg: 'bg-[#1b7a4b]/12',
        badgeBg: 'bg-[#1b7a4b]/15 text-[#1b7a4b] border-[#1b7a4b]/30',
        shadow: 'shadow-[0_2px_8px_rgba(27,122,75,0.1)]',
        focusRing: 'focus-visible:outline-[#1b7a4b] focus-visible:ring-[#1b7a4b]/30',
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
          } ${sizeClasses} ${variantConfig.text} ${variantConfig.bg} ${variantConfig.border} ${
            fullWidth ? 'w-full' : ''
          } ${className}`}
          style={{
            transformOrigin: 'center center',
          }}
          {...props}
        >
          {/* Action Tile Presentation with Dual Labels */}
          {isActionTile ? (
            <div className="flex items-center gap-2.5 w-full text-left py-0.5">
              {icon && (
                <div className="p-2 rounded-xl bg-[#2d4a3e]/8 border border-[#2d4a3e]/15 flex items-center justify-center flex-none">
                  {icon}
                </div>
              )}
              <div className="flex flex-col min-w-0 flex-1">
                <span className="font-semibold text-xs tracking-tight truncate leading-tight">
                  {children}
                </span>
                {sublabel && (
                  <span className="text-[10px] text-[#4e6357] font-normal truncate mt-0.5 leading-none">
                    {sublabel}
                  </span>
                )}
              </div>
            </div>
          ) : (
            /* Standard Compact Button Presentation */
            <div className="flex items-center gap-1.5 justify-center">
              {badge && (
                <span
                  className={`text-[9.5px] uppercase font-mono px-1.5 py-0.2 rounded-full border ${variantConfig.badgeBg} font-semibold`}
                >
                  {badge}
                </span>
              )}
              {icon && <span className="flex-none">{icon}</span>}
              <span className="truncate">{children}</span>
            </div>
          )}
        </button>

        {/* Ambient Under-Button Shadow */}
        <div
          className="liquid-button-shadow"
          aria-hidden="true"
          style={{
            borderRadius: isActionTile ? '16px' : '9999px',
          }}
        />
      </div>
    );
  }
);

LiquidGlassButton.displayName = 'LiquidGlassButton';

export default LiquidGlassButton;
