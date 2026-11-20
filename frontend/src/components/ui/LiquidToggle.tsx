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
        className={`liquid-toggle relative cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 focus-visible:ring-2 focus-visible:ring-sky-400/40 ${
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
            transition: 'opacity 0.15s ease',
          } as React.CSSProperties
        }
      >
        {/* Background track & indicator — Clean Empty Liquid Glass */}
        <div
          className="indicator absolute inset-0 rounded-full"
          style={{
            background: checked
              ? 'linear-gradient(-75deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.32), rgba(255, 255, 255, 0.15))'
              : 'rgba(255, 255, 255, 0.08)',
            boxShadow: checked
              ? 'inset 0 1px 1px rgba(255, 255, 255, 0.6), 0 0 12px rgba(255, 255, 255, 0.25)'
              : 'inset 0 1px 2px rgba(0, 0, 0, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            transition: 'background 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease',
          }}
        />

        {/* Gooey Filtered Liquid Fluid */}
        <div
          className="liquids absolute inset-0 rounded-full overflow-hidden pointer-events-none"
          style={{ filter: 'url(#goo)' }}
        >
          <div
            className="liquid__track absolute top-0 bottom-0 rounded-full"
            style={{
              left: checked ? `${width - height + border}px` : `${border}px`,
              width: `${height - border * 2}px`,
              height: `${height - border * 2}px`,
              margin: 'auto 0',
              background: checked ? '#ffffff' : 'rgba(255, 255, 255, 0.7)',
              boxShadow:
                '0 2px 6px rgba(0,0,0,0.35), inset 0 1px 1px rgba(255,255,255,0.9)',
              transition: 'left 0.2s cubic-bezier(0.25, 1, 0.5, 1), background 0.2s ease',
            }}
          />
        </div>

        {/* Specular Liquid Bead Highlight */}
        <div
          className="absolute top-0 bottom-0 rounded-full pointer-events-none"
          style={{
            left: checked ? `${width - height + border}px` : `${border}px`,
            width: `${height - border * 2}px`,
            height: `${height - border * 2}px`,
            margin: 'auto 0',
            boxShadow:
              'inset 1px 1px 2px rgba(255,255,255,0.8), inset -1px -1px 2px rgba(0,0,0,0.2)',
            transition: 'left 0.2s cubic-bezier(0.25, 1, 0.5, 1)',
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
