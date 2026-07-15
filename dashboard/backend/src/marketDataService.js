/**
 * Asset Flow Engine
 *
 * Owns the in-memory market state and the Inflow/Outflow calculation described
 * in the spec: flow_amount = (current_price - previous_price) * volume.
 *
 * This module currently drives itself with a randomized walk so the rest of
 * the stack (API, websocket, UI) can be built and demoed end-to-end without a
 * live market data vendor. Swap `tick()` for a real feed by writing new
 * price/volume samples into `state.assets` before calling `computeFlow`.
 */

const CATEGORIES = {
  FOREX: 'FOREX',
  STOCKS: 'STOCKS',
  BONDS: 'BONDS',
  COMMODITIES: 'COMMODITIES',
  CRYPTO: 'CRYPTO'
};

// Seed universe. `volatility` is the per-tick max % price move.
// `baseVolume` approximates traded size per tick window (used to size flow $).
const SEED_ASSETS = [
  { id: 'FOREX_DXY', category: CATEGORIES.FOREX, ticker: 'DXY', name: 'US Dollar Index', price: 104.32, volatility: 0.15, baseVolume: 4_500_000_000 },
  { id: 'FOREX_EURUSD', category: CATEGORIES.FOREX, ticker: 'EUR/USD', name: 'Euro / US Dollar', price: 1.0875, volatility: 0.2, baseVolume: 8_200_000_000 },
  { id: 'FOREX_GBPUSD', category: CATEGORIES.FOREX, ticker: 'GBP/USD', name: 'British Pound / US Dollar', price: 1.2695, volatility: 0.22, baseVolume: 3_800_000_000 },
  { id: 'FOREX_USDJPY', category: CATEGORIES.FOREX, ticker: 'USD/JPY', name: 'US Dollar / Japanese Yen', price: 157.42, volatility: 0.25, baseVolume: 5_100_000_000 },

  { id: 'STOCKS_NASDAQ', category: CATEGORIES.STOCKS, ticker: 'NASDAQ', name: 'Nasdaq Composite', price: 26177, volatility: 0.35, baseVolume: 65_000_000_000 },
  { id: 'STOCKS_SP500', category: CATEGORIES.STOCKS, ticker: 'S&P 500', name: 'S&P 500', price: 6180, volatility: 0.3, baseVolume: 120_000_000_000 },
  { id: 'STOCKS_DOWJONES', category: CATEGORIES.STOCKS, ticker: 'DOW', name: 'Dow Jones Industrial', price: 43850, volatility: 0.25, baseVolume: 40_000_000_000 },

  { id: 'BONDS_US10Y', category: CATEGORIES.BONDS, ticker: 'US10Y', name: 'US 10-Year Treasury', price: 4.28, volatility: 0.6, baseVolume: 22_000_000_000 },
  { id: 'BONDS_US2Y', category: CATEGORIES.BONDS, ticker: 'US2Y', name: 'US 2-Year Treasury', price: 4.71, volatility: 0.5, baseVolume: 18_000_000_000 },

  { id: 'COMMODITIES_GOLD', category: CATEGORIES.COMMODITIES, ticker: 'XAU/USD', name: 'Gold Spot', price: 2415.6, volatility: 0.3, baseVolume: 15_000_000_000 },
  { id: 'COMMODITIES_SILVER', category: CATEGORIES.COMMODITIES, ticker: 'XAG/USD', name: 'Silver Spot', price: 30.85, volatility: 0.5, baseVolume: 4_000_000_000 },
  { id: 'COMMODITIES_OIL', category: CATEGORIES.COMMODITIES, ticker: 'WTI', name: 'Crude Oil WTI', price: 78.4, volatility: 0.6, baseVolume: 9_500_000_000 },

  { id: 'CRYPTO_BTC', category: CATEGORIES.CRYPTO, ticker: 'BTC', name: 'Bitcoin', price: 96500, volatility: 1.2, baseVolume: 28_000_000_000 },
  { id: 'CRYPTO_ETH', category: CATEGORIES.CRYPTO, ticker: 'ETH', name: 'Ethereum', price: 3350, volatility: 1.6, baseVolume: 14_000_000_000 },
  { id: 'CRYPTO_SOL', category: CATEGORIES.CRYPTO, ticker: 'SOL', name: 'Solana', price: 148.2, volatility: 2.2, baseVolume: 3_200_000_000 },
  { id: 'CRYPTO_AAVE', category: CATEGORIES.CRYPTO, ticker: 'AAVE', name: 'Aave', price: 85.5, volatility: 3.5, baseVolume: 210_000_000 },
  { id: 'CRYPTO_LINK', category: CATEGORIES.CRYPTO, ticker: 'LINK', name: 'Chainlink', price: 14.7, volatility: 3.0, baseVolume: 350_000_000 },
  { id: 'CRYPTO_ARB', category: CATEGORIES.CRYPTO, ticker: 'ARB', name: 'Arbitrum', price: 0.62, volatility: 4.0, baseVolume: 90_000_000 }
];

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

function round(value, decimals) {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

class MarketDataService {
  constructor() {
    this.assets = SEED_ASSETS.map((seed) => ({
      ...seed,
      previousPrice: seed.price
    }));

    this.globalLiquidity = {
      fed_balance: -36.5, // net liquidity delta, $B, illustrative
      m2_growth: 2.1, // % YoY
      reverse_repo: 412.8 // $B outstanding
    };
  }

  /** Advances the simulated market one step and recomputes flow for every asset. */
  tick() {
    this.assets = this.assets.map((asset) => this._tickAsset(asset));
    this._tickGlobalLiquidity();
    return this.getSnapshot();
  }

  _tickAsset(asset) {
    const previousPrice = asset.price;
    const pctMove = randomBetween(-asset.volatility, asset.volatility) / 100;
    const nextPrice = Math.max(previousPrice * (1 + pctMove), 0.0001);
    const volume = asset.baseVolume * randomBetween(0.7, 1.3);

    return {
      ...asset,
      previousPrice,
      price: nextPrice,
      lastVolume: volume
    };
  }

  _tickGlobalLiquidity() {
    this.globalLiquidity = {
      fed_balance: round(this.globalLiquidity.fed_balance + randomBetween(-0.4, 0.4), 2),
      m2_growth: round(this.globalLiquidity.m2_growth + randomBetween(-0.05, 0.05), 2),
      reverse_repo: round(Math.max(this.globalLiquidity.reverse_repo + randomBetween(-8, 8), 0), 2)
    };
  }

  /** Builds the API/websocket payload described in the spec. */
  getSnapshot() {
    return {
      timestamp: new Date().toISOString(),
      global_liquidity: { ...this.globalLiquidity },
      assets: this.assets.map((asset) => this._toPayload(asset))
    };
  }

  _toPayload(asset) {
    const { price, previousPrice, lastVolume } = asset;
    const changePercent = previousPrice ? ((price - previousPrice) / previousPrice) * 100 : 0;
    const flowAmount = (price - previousPrice) * (lastVolume || asset.baseVolume);
    const flowStatus = flowAmount > 0 ? 'IN' : flowAmount < 0 ? 'OUT' : 'NEUTRAL';

    return {
      id: asset.id,
      category: asset.category,
      ticker: asset.ticker,
      name: asset.name,
      price: round(price, price < 10 ? 4 : 2),
      change_percent: round(changePercent, 2),
      flow_status: flowStatus,
      flow_amount: Math.round(flowAmount)
    };
  }
}

module.exports = { MarketDataService, CATEGORIES };
