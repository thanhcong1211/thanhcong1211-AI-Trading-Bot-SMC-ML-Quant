'use client';

import { Asset } from '@/lib/types';
import { formatFlowAmount, formatPercent, formatPrice } from '@/lib/format';
import { FlashValue } from './FlashValue';

function flowColorClass(status: Asset['flow_status']) {
  if (status === 'IN') return 'text-terminal-in text-glow-in';
  if (status === 'OUT') return 'text-terminal-out text-glow-out';
  return 'text-terminal-neutral';
}

function changeColorClass(changePercent: number) {
  if (changePercent > 0) return 'text-terminal-in';
  if (changePercent < 0) return 'text-terminal-out';
  return 'text-terminal-neutral';
}

interface AssetTableProps {
  title: string;
  assets: Asset[];
}

export function AssetTable({ title, assets }: AssetTableProps) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-widest text-terminal-neutral">
        <span className="h-1.5 w-1.5 rounded-full bg-terminal-amber" />
        {title}
      </div>
      <table className="w-full border-collapse text-xs sm:text-sm">
        <thead>
          <tr className="border-b border-terminal-border text-left text-terminal-neutral">
            <th className="py-1.5 pr-2 font-normal">Ticker</th>
            <th className="py-1.5 pr-2 text-right font-normal">Price</th>
            <th className="py-1.5 pr-2 text-right font-normal">Chg %</th>
            <th className="py-1.5 text-right font-normal">Net Flow</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id} className="border-b border-terminal-border/50 hover:bg-white/[0.02]">
              <td className="py-1.5 pr-2">
                <div className="font-semibold text-gray-200">{asset.ticker}</div>
                <div className="text-[10px] text-terminal-neutral">{asset.name}</div>
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                <FlashValue value={asset.price} className="text-gray-200">
                  {formatPrice(asset.price)}
                </FlashValue>
              </td>
              <td className={`py-1.5 pr-2 text-right tabular-nums ${changeColorClass(asset.change_percent)}`}>
                <FlashValue value={asset.change_percent}>{formatPercent(asset.change_percent)}</FlashValue>
              </td>
              <td className={`py-1.5 text-right tabular-nums font-semibold ${flowColorClass(asset.flow_status)}`}>
                <FlashValue value={asset.flow_amount}>{formatFlowAmount(asset.flow_amount)}</FlashValue>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
