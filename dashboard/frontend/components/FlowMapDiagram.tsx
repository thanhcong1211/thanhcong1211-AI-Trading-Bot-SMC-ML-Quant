'use client';

import { AssetClass } from '@/lib/types';
import { formatFlowAmount } from '@/lib/format';
import { FlashValue } from './FlashValue';

interface FlowMapDiagramProps {
  assetClasses: AssetClass[];
}

const COLUMN_CENTERS_4 = [12.5, 37.5, 62.5, 87.5];

export function FlowMapDiagram({ assetClasses }: FlowMapDiagramProps) {
  return (
    <div className="px-3">
      {/* Connector lines: hub -> each asset class node */}
      <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="h-16 w-full overflow-visible">
        {assetClasses.map((cls, i) => {
          const x = COLUMN_CENTERS_4[i] ?? (i + 0.5) * (100 / assetClasses.length);
          const isIn = cls.flow_status === 'IN';
          const color = isIn ? '#00ff41' : cls.flow_status === 'OUT' ? '#ff3333' : '#7a8a80';
          const pathId = `flow-path-${cls.id}`;
          const d = `M50,0 C${(50 + x) / 2},4 ${(50 + x) / 2},28 ${x},32`;

          return (
            <g key={cls.id}>
              <path id={pathId} d={d} fill="none" stroke={color} strokeWidth={0.4} opacity={0.55} />
              <circle r={0.9} fill={color}>
                <animateMotion dur={`${2.4 + i * 0.3}s`} repeatCount="indefinite">
                  <mpath href={`#${pathId}`} />
                </animateMotion>
              </circle>
            </g>
          );
        })}
      </svg>

      {/* Asset class hub nodes */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {assetClasses.map((cls) => {
          const isIn = cls.flow_status === 'IN';
          const colorClass = isIn ? 'border-terminal-in/60 text-terminal-in text-glow-in' : 'border-terminal-out/60 text-terminal-out text-glow-out';

          return (
            <div key={cls.id} className={`rounded border bg-black/40 px-2 py-2 text-center ${colorClass}`}>
              <div className="text-xs font-bold uppercase tracking-widest text-gray-300">{cls.label}</div>
              <div className="text-lg font-bold tabular-nums">
                <FlashValue value={cls.flow_amount}>{formatFlowAmount(cls.flow_amount)}</FlashValue>
              </div>
              <div className="text-[10px] font-semibold uppercase tracking-wider">
                {cls.flow_status === 'NEUTRAL' ? 'FLAT' : `${cls.flow_status} ${formatFlowAmount(Math.abs(cls.flow_amount)).replace('+$', '$')}`}
              </div>
            </div>
          );
        })}
      </div>

      {/* Breakdown grid per asset class */}
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {assetClasses.map((cls) => (
          <div key={cls.id} className="flex flex-col gap-1.5">
            {cls.children.map((child) => {
              const isIn = child.flow_status === 'IN';
              return (
                <div key={child.id} className="rounded border border-terminal-border bg-terminal-panel/60 px-2 py-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-semibold text-gray-200">{child.ticker}</span>
                    <span className={isIn ? 'text-terminal-in' : 'text-terminal-out'}>
                      <FlashValue value={child.change_percent}>
                        {child.change_percent > 0 ? '+' : ''}
                        {child.change_percent.toFixed(2)}%
                      </FlashValue>
                    </span>
                  </div>
                  {typeof child.allocation_pct === 'number' && (
                    <div className="text-[9px] uppercase tracking-wide text-terminal-neutral">
                      Alloc {child.allocation_pct}% &middot; {child.price.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                    </div>
                  )}
                  <div className={`text-[10px] font-semibold ${isIn ? 'text-terminal-in' : 'text-terminal-out'}`}>
                    <FlashValue value={child.flow_amount}>{formatFlowAmount(child.flow_amount)}</FlashValue>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
