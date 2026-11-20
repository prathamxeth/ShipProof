'use client';

import React from 'react';

export interface LiquidToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  size?: 'sm' | 'md';
}

export function LiquidToggle({
  checked,
  onChange,
  disabled = false,
  label,
  size = 'md',
}: LiquidToggleProps) {
  const isSm = size === 'sm';
  const width = isSm ? 54 : 68;
  const height = isSm ? 26 : 32;
  const border = isSm ? 3 : 4;

  const handleClick = () => {
    if (disabled) return;
    onChange(!checked);
  };

  return (
    <div className="inline-flex items-center gap-2.5 select-none">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={handleClick}
        className={`liquid-toggle relative cursor-pointer outline-none transition-all duration-300 ${
          disabled ? 'opacity-40 cursor-not-allowed' : ''
        }`}
        style={
          {
            '--width': width,
            '--height': height,
            '--border': `${border}px`,
            '--complete': checked ? '100' : '0',
            width: `${width}px`,
            height: `${height}px`,
          } as React.CSSProperties
        }
      >
        {/* Background track & indicator */}
        <div
          className="indicator absolute inset-0 rounded-full transition-colors duration-300"
          style={{
            background: checked
              ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
              : 'rgba(255, 255, 255, 0.1)',
            boxShadow: checked
              ? '0 0 14px rgba(16, 185, 129, 0.4), inset 0 1px 1px rgba(255, 255, 255, 0.5)'
              : 'inset 0 1px 2px rgba(0, 0, 0, 0.5)',
          }}
        />

        {/* Gooey Filtered Liquid Fluid */}
        <div
          className="liquids absolute inset-0 rounded-full overflow-hidden pointer-events-none"
          style={{ filter: 'url(#goo)' }}
        >
          <div
            className="liquid__track absolute top-0 bottom-0 rounded-full transition-all duration-300 ease-out"
            style={{
              left: checked ? `${width - height + border}px` : `${border}px`,
              width: `${height - border * 2}px`,
              height: `${height - border * 2}px`,
              margin: 'auto 0',
              background: checked ? '#ffffff' : 'rgba(255, 255, 255, 0.7)',
              boxShadow:
                '0 2px 6px rgba(0,0,0,0.35), inset 0 1px 1px rgba(255,255,255,0.9)',
            }}
          />
        </div>

        {/* Specular Liquid Bead Highlight */}
        <div
          className="absolute top-0 bottom-0 rounded-full pointer-events-none transition-all duration-300 ease-out"
          style={{
            left: checked ? `${width - height + border}px` : `${border}px`,
            width: `${height - border * 2}px`,
            height: `${height - border * 2}px`,
            margin: 'auto 0',
            boxShadow:
              'inset 1px 1px 2px rgba(255,255,255,0.8), inset -1px -1px 2px rgba(0,0,0,0.2)',
          }}
        />
      </button>

      {label && (
        <span
          onClick={handleClick}
          className="text-xs font-mono text-zinc-300 cursor-pointer"
        >
          {label}
        </span>
      )}
    </div>
  );
}

export default LiquidToggle;
