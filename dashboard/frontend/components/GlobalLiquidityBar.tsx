'use client';

import { GlobalLiquidity } from '@/lib/types';
import { formatTimestamp } from '@/lib/format';
import { FlashValue } from './FlashValue';

interface LiquidityBadgeProps {
  label: string;
  value: number;
  suffix: string;
  positiveIsGood: boolean;
}

function LiquidityBadge({ label, value, suffix, positiveIsGood }: LiquidityBadgeProps) {
  const isGood = positiveIsGood ? value >= 0 : value < 0;
  const colorClass = isGood ? 'text-terminal-in text-glow-in border-terminal-in/40' : 'text-terminal-out text-glow-out border-terminal-out/40';

  return (
    <div className={`flex items-center gap-2 rounded border bg-black/30 px-3 py-1.5 ${colorClass}`}>
      <span className="text-[10px] uppercase tracking-widest text-terminal-neutral">{label}</span>
      <FlashValue value={value} className="text-sm font-bold tabular-nums">
        {value > 0 ? '+' : ''}
        {value.toFixed(2)}
        {suffix}
      </FlashValue>
    </div>
  );
}

interface GlobalLiquidityBarProps {
  liquidity: GlobalLiquidity;
  timestamp: string | null;
  connectionStatus: 'connecting' | 'live' | 'offline';
}

export function GlobalLiquidityBar({ liquidity, timestamp, connectionStatus }: GlobalLiquidityBarProps) {
  const statusMeta = {
    connecting: { label: 'CONNECTING', color: 'bg-terminal-amber' },
    live: { label: 'LIVE', color: 'bg-terminal-in' },
    offline: { label: 'OFFLINE', color: 'bg-terminal-out' }
  }[connectionStatus];

  return (
    <header className="sticky top-0 z-10 flex w-full flex-wrap items-center justify-between gap-3 border-b border-terminal-border bg-terminal-bg/95 px-4 py-3">
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-bold uppercase tracking-widest text-gray-200 sm:text-base">
          Global Liquidity &amp; Asset Flow
        </h1>
        <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-terminal-neutral">
          <span className={`h-1.5 w-1.5 animate-pulse rounded-full ${statusMeta.color}`} />
          {statusMeta.label}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <LiquidityBadge label="Fed Balance Δ" value={liquidity.fed_balance} suffix="B" positiveIsGood />
        <LiquidityBadge label="M2 Growth" value={liquidity.m2_growth} suffix="%" positiveIsGood />
        <LiquidityBadge label="Reverse Repo" value={liquidity.reverse_repo} suffix="B" positiveIsGood={false} />
        {timestamp && (
          <span className="text-[10px] text-terminal-neutral">Last update: {formatTimestamp(timestamp)}</span>
        )}
      </div>
    </header>
  );
}
