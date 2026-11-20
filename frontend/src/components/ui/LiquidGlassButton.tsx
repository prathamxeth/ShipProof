'use client';

import React from 'react';

export interface LiquidGlassButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  variant?: 'primary' | 'glass' | 'danger' | 'emerald';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
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
      className = '',
      disabled,
      ...props
    },
    ref
  ) => {
    // Sizing scales
    const sizeClasses = {
      sm: 'text-[11px] py-1.5 px-3',
      md: 'text-xs py-2 px-4',
      lg: 'text-sm py-2.5 px-6',
    }[size];

    // Variant color accents for the gleam and text
    const variantClasses = {
      primary:
        'text-white shadow-blue-500/20 [--btn-accent:rgba(24,99,220,0.6)] [--btn-gleam:rgba(147,197,253,0.7)]',
      glass:
        'text-zinc-100 shadow-white/5 [--btn-accent:rgba(255,255,255,0.15)] [--btn-gleam:rgba(255,255,255,0.6)]',
      danger:
        'text-rose-100 shadow-rose-500/20 [--btn-accent:rgba(225,29,72,0.6)] [--btn-gleam:rgba(253,164,175,0.7)]',
      emerald:
        'text-emerald-100 shadow-emerald-500/20 [--btn-accent:rgba(16,185,129,0.6)] [--btn-gleam:rgba(110,231,183,0.7)]',
    }[variant];

    return (
      <div
        className={`liquid-button-wrap inline-block relative ${
          fullWidth ? 'w-full' : ''
        } ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <button
          ref={ref}
          disabled={disabled}
          className={`liquid-glass-btn relative inline-flex items-center justify-center font-medium font-sans cursor-pointer select-none transition-all duration-300 ${sizeClasses} ${variantClasses} ${
            fullWidth ? 'w-full' : ''
          } ${className}`}
          {...props}
        >
          <span className="liquid-btn-content relative z-10 flex items-center justify-center gap-2">
            {children}
          </span>
        </button>
        {/* Blurred ambient shadow */}
        <div className="liquid-button-shadow" aria-hidden="true" />
      </div>
    );
  }
);

LiquidGlassButton.displayName = 'LiquidGlassButton';

export default LiquidGlassButton;
