export function formatPrice(price: number): string {
  const decimals = price < 10 ? 4 : price < 1000 ? 2 : 2;
  return price.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

export function formatPercent(pct: number): string {
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

/** Compact $ formatting: 8500000000 -> "$8.50B", -17000000 -> "-$17.00M" */
export function formatFlowAmount(amount: number): string {
  const abs = Math.abs(amount);
  const sign = amount < 0 ? '-' : '+';
  let value: string;

  if (abs >= 1_000_000_000) {
    value = `${(abs / 1_000_000_000).toFixed(2)}B`;
  } else if (abs >= 1_000_000) {
    value = `${(abs / 1_000_000).toFixed(2)}M`;
  } else if (abs >= 1_000) {
    value = `${(abs / 1_000).toFixed(2)}K`;
  } else {
    value = abs.toFixed(0);
  }

  return `${sign}$${value}`;
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString('en-US', { hour12: false });
}
