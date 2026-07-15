'use client';

import { formatTimestamp } from '@/lib/format';

interface GlobalLiquidityBarProps {
  timestamp: string | null;
  connectionStatus: 'connecting' | 'live' | 'offline';
}

export function GlobalLiquidityBar({ timestamp, connectionStatus }: GlobalLiquidityBarProps) {
  const statusMeta = {
    connecting: { label: 'CONNECTING', color: 'bg-terminal-amber' },
    live: { label: 'LIVE', color: 'bg-terminal-in' },
    offline: { label: 'OFFLINE', color: 'bg-terminal-out' }
  }[connectionStatus];

  return (
    <header className="sticky top-0 z-10 flex w-full flex-wrap items-center justify-between gap-3 border-b border-terminal-border bg-terminal-bg/95 px-4 py-2.5">
      <h1 className="text-sm font-bold uppercase tracking-widest text-gray-200 sm:text-base">
        Global Liquidity &amp; Asset Flow
      </h1>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-terminal-neutral">
          <span className={`h-1.5 w-1.5 animate-pulse rounded-full ${statusMeta.color}`} />
          {statusMeta.label}
        </span>
        {timestamp && (
          <span className="text-[10px] text-terminal-neutral">Last update: {formatTimestamp(timestamp)}</span>
        )}
      </div>
    </header>
  );
}
