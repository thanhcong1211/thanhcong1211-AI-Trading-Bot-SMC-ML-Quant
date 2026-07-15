'use client';

interface BottomTickerProps {
  alerts: string[];
}

export function BottomTicker({ alerts }: BottomTickerProps) {
  if (alerts.length === 0) return null;

  const loopItems = [...alerts, ...alerts];

  return (
    <div className="fixed inset-x-0 bottom-0 z-20 overflow-hidden border-t border-terminal-border bg-black/90 py-1.5 backdrop-blur-sm">
      <div className="animate-ticker flex w-max gap-10 whitespace-nowrap text-xs font-semibold uppercase tracking-widest">
        {loopItems.map((alert, i) => (
          <span key={i} className="flex items-center gap-2 text-terminal-amber">
            <span className="h-1.5 w-1.5 rounded-full bg-terminal-amber" />
            {alert}
          </span>
        ))}
      </div>
    </div>
  );
}
