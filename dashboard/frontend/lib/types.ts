export type AssetCategory = 'CURRENCY' | 'STOCKS' | 'BONDS' | 'COMMODITIES' | 'CRYPTO';

export type FlowStatus = 'IN' | 'OUT' | 'NEUTRAL';

export type CryptoTier = 'BIG_CAP' | 'MID_CAP' | 'MEME';

export interface Asset {
  id: string;
  category: AssetCategory;
  ticker: string;
  name: string;
  price: number;
  change_percent: number;
  flow_status: FlowStatus;
  flow_amount: number;
  allocation_pct?: number;
  tier?: CryptoTier;
  accent?: string;
}

export interface AssetClass {
  id: 'STOCKS' | 'BONDS' | 'COMMODITIES' | 'CRYPTO';
  label: string;
  flow_amount: number;
  flow_status: FlowStatus;
  children: Asset[];
}

export interface GlobalLiquidity {
  fed_balance: number;
  m2_growth: number;
  reverse_repo: number;
  qe_qt_status: string;
}

export interface MarketFlowSnapshot {
  timestamp: string;
  global_liquidity: GlobalLiquidity;
  currencies: Asset[];
  asset_classes: AssetClass[];
  crypto_by_tier: Record<CryptoTier, Asset[]>;
  alerts: string[];
}
