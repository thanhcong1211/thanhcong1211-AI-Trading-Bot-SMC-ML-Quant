'use client';

import { Asset } from '@/lib/types';
import { formatFlowAmount } from '@/lib/format';
import { FlashValue } from './FlashValue';

interface CurrencyLiquidityRowProps {
  currencies: Asset[];
}

export function CurrencyLiquidityRow({ currencies }: CurrencyLiquidityRowProps) {
  return (
    <div className="px-3">
      <div className="mb-1.5 text-center text-[11px] font-bold uppercase tracking-widest text-terminal-neutral">
        Currency Liquidity
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {currencies.map((ccy) => (
          <div
            key={ccy.id}
            className="min-w-[110px] rounded border bg-black/40 px-3 py-1.5 text-center"
            style={{ borderColor: `${ccy.accent ?? '#7a8a80'}66` }}
          >
            <div className="flex items-center justify-center gap-1.5 text-sm font-bold" style={{ color: ccy.accent }}>
              <span>{ccy.ticker}</span>
              <FlashValue value={ccy.price} className="tabular-nums">
                {ccy.price.toLocaleString('en-US', { minimumFractionDigits: ccy.price < 10 ? 4 : 2, maximumFractionDigits: ccy.price < 10 ? 4 : 2 })}
              </FlashValue>
            </div>
            <div className={`text-xs font-semibold tabular-nums ${ccy.flow_amount >= 0 ? 'text-terminal-in' : 'text-terminal-out'}`}>
              <FlashValue value={ccy.flow_amount}>{formatFlowAmount(ccy.flow_amount)}</FlashValue>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
