'use client';

import { GlobalLiquidity } from '@/lib/types';
import { FlashValue } from './FlashValue';

interface LiquidityHeroProps {
  liquidity: GlobalLiquidity;
}

const TAGS = ['QE', 'QT', 'M2', 'RRP', 'FED'];

export function LiquidityHero({ liquidity }: LiquidityHeroProps) {
  return (
    <div className="flex flex-col items-center gap-2 py-4">
      <div className="rounded-md border border-terminal-in/50 bg-black/40 px-6 py-3 text-center shadow-glow-in">
        <div className="text-sm font-bold uppercase tracking-[0.3em] text-terminal-in text-glow-in sm:text-base">
          Global Liquidity
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-1.5 text-[10px] uppercase tracking-widest text-terminal-neutral">
          {TAGS.map((tag, i) => (
            <span key={tag} className="flex items-center gap-1.5">
              <span className={tag === liquidity.qe_qt_status ? 'text-terminal-amber' : ''}>{tag}</span>
              {i < TAGS.length - 1 && <span className="text-terminal-border">·</span>}
            </span>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-3 text-[11px]">
          <span className="text-terminal-neutral">
            Fed Δ{' '}
            <FlashValue value={liquidity.fed_balance} className={liquidity.fed_balance >= 0 ? 'text-terminal-in' : 'text-terminal-out'}>
              {liquidity.fed_balance > 0 ? '+' : ''}
              {liquidity.fed_balance.toFixed(2)}B
            </FlashValue>
          </span>
          <span className="text-terminal-neutral">
            M2{' '}
            <FlashValue value={liquidity.m2_growth} className={liquidity.m2_growth >= 0 ? 'text-terminal-in' : 'text-terminal-out'}>
              {liquidity.m2_growth > 0 ? '+' : ''}
              {liquidity.m2_growth.toFixed(2)}%
            </FlashValue>
          </span>
          <span className="text-terminal-neutral">
            RRP{' '}
            <FlashValue value={liquidity.reverse_repo} className="text-terminal-amber">
              {liquidity.reverse_repo.toFixed(1)}B
            </FlashValue>
          </span>
        </div>
      </div>

      <div className="h-4 w-px bg-terminal-in/40" />
      <div className="rounded-full border border-terminal-in/40 bg-black/40 px-4 py-0.5 text-[10px] font-bold uppercase tracking-widest text-terminal-in text-glow-in">
        Liquidity
      </div>
    </div>
  );
}
