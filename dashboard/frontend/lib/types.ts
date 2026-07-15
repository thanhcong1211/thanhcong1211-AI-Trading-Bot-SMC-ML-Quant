export type AssetCategory = 'FOREX' | 'STOCKS' | 'BONDS' | 'COMMODITIES' | 'CRYPTO';

export type FlowStatus = 'IN' | 'OUT' | 'NEUTRAL';

export interface Asset {
  id: string;
  category: AssetCategory;
  ticker: string;
  name: string;
  price: number;
  change_percent: number;
  flow_status: FlowStatus;
  flow_amount: number;
}

export interface GlobalLiquidity {
  fed_balance: number;
  m2_growth: number;
  reverse_repo: number;
}

export interface MarketFlowSnapshot {
  timestamp: string;
  global_liquidity: GlobalLiquidity;
  assets: Asset[];
}
