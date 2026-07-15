'use client';

import { Asset, CryptoTier } from '@/lib/types';
import { formatFlowAmount } from '@/lib/format';
import { FlashValue } from './FlashValue';

interface AltcoinFlowBoardProps {
  cryptoByTier: Record<CryptoTier, Asset[]>;
}

const TIER_LABELS: Record<CryptoTier, string> = {
  BIG_CAP: 'Big Cap',
  MID_CAP: 'Mid Cap',
  MEME: 'Meme'
};

const TIER_COLORS: Record<CryptoTier, string> = {
  BIG_CAP: 'text-terminal-in',
  MID_CAP: 'text-terminal-amber',
  MEME: 'text-purple-400'
};

export function AltcoinFlowBoard({ cryptoByTier }: AltcoinFlowBoardProps) {
  const tiers: CryptoTier[] = ['BIG_CAP', 'MID_CAP', 'MEME'];

  return (
    <div className="px-3 py-3">
      <div className="mb-2 text-center text-[11px] font-bold uppercase tracking-widest text-terminal-neutral">
        Top Altcoins by Flow — per category
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {tiers.map((tier) => (
          <div key={tier} className="rounded border border-terminal-border bg-terminal-panel/40 p-2">
            <div className={`mb-1.5 text-center text-xs font-bold uppercase tracking-widest ${TIER_COLORS[tier]}`}>
              {TIER_LABELS[tier]}
            </div>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
              {cryptoByTier[tier]?.map((coin) => {
                const isIn = coin.flow_status === 'IN';
                return (
                  <div key={coin.id} className="rounded border border-terminal-border bg-black/40 px-1.5 py-1 text-center">
                    <div className="text-[11px] font-bold text-gray-200">{coin.ticker}</div>
                    <div className={`text-[10px] font-semibold ${isIn ? 'text-terminal-in' : 'text-terminal-out'}`}>
                      <FlashValue value={coin.flow_amount}>{formatFlowAmount(coin.flow_amount)}</FlashValue>
                    </div>
                    <div className={`text-[9px] ${isIn ? 'text-terminal-in' : 'text-terminal-out'}`}>
                      <FlashValue value={coin.change_percent}>
                        {coin.change_percent > 0 ? '+' : ''}
                        {coin.change_percent.toFixed(2)}%
                      </FlashValue>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
