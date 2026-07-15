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
 *
 * Output shape is a "liquidity flow map": a Global Liquidity hub, a Currency
 * Liquidity row, and asset-class nodes (STOCKS / BONDS / COMMODITIES /
 * CRYPTO) whose net flow is the sum of their children — mirroring the
 * rotation-map style dashboard the UI renders.
 */

const CATEGORIES = {
  CURRENCY: 'CURRENCY',
  STOCKS: 'STOCKS',
  BONDS: 'BONDS',
  COMMODITIES: 'COMMODITIES',
  CRYPTO: 'CRYPTO'
};

const CRYPTO_TIERS = {
  BIG_CAP: 'BIG_CAP',
  MID_CAP: 'MID_CAP',
  MEME: 'MEME'
};

// Seed universe. `volatility` is the per-tick max % price move.
// `baseVolume` approximates traded size per tick window (used to size flow $).
// `allocationPct` / `tier` only drive display grouping, not the flow math.
const SEED_ASSETS = [
  { id: 'CCY_USD', category: CATEGORIES.CURRENCY, ticker: 'USD', name: 'US Dollar Index (DXY)', price: 104.32, volatility: 0.15, baseVolume: 4_500_000_000, accent: '#4da3ff' },
  { id: 'CCY_EUR', category: CATEGORIES.CURRENCY, ticker: 'EUR', name: 'Euro / US Dollar', price: 1.0875, volatility: 0.2, baseVolume: 8_200_000_000, accent: '#00ff41' },
  { id: 'CCY_JPY', category: CATEGORIES.CURRENCY, ticker: 'JPY', name: 'US Dollar / Japanese Yen', price: 157.42, volatility: 0.25, baseVolume: 5_100_000_000, accent: '#ff3333' },
  { id: 'CCY_CNY', category: CATEGORIES.CURRENCY, ticker: 'CNY', name: 'US Dollar / Chinese Yuan', price: 7.242, volatility: 0.12, baseVolume: 3_000_000_000, accent: '#ffb000' },
  { id: 'CCY_GBP', category: CATEGORIES.CURRENCY, ticker: 'GBP', name: 'British Pound / US Dollar', price: 1.2695, volatility: 0.22, baseVolume: 3_800_000_000, accent: '#c084fc' },

  { id: 'STOCKS_NASDAQ', category: CATEGORIES.STOCKS, ticker: 'NASDAQ', name: 'Nasdaq Composite', price: 26177, volatility: 0.35, baseVolume: 65_000_000_000, allocationPct: 15 },
  { id: 'STOCKS_SP500', category: CATEGORIES.STOCKS, ticker: 'S&P 500', name: 'S&P 500', price: 6180, volatility: 0.3, baseVolume: 120_000_000_000, allocationPct: 30 },
  { id: 'STOCKS_DOWJONES', category: CATEGORIES.STOCKS, ticker: 'DOW', name: 'Dow Jones Industrial', price: 43850, volatility: 0.25, baseVolume: 40_000_000_000, allocationPct: 7 },
  { id: 'STOCKS_OTHERS', category: CATEGORIES.STOCKS, ticker: 'OTHERS', name: 'Nikkei / DAX / FTSE / EM', price: 7534, volatility: 0.3, baseVolume: 30_000_000_000, allocationPct: 48 },

  { id: 'BONDS_US2Y', category: CATEGORIES.BONDS, ticker: 'US2Y', name: 'US 2-Year Treasury', price: 4.71, volatility: 0.5, baseVolume: 18_000_000_000, allocationPct: 8 },
  { id: 'BONDS_US10Y', category: CATEGORIES.BONDS, ticker: 'US10Y', name: 'US 10-Year Treasury', price: 4.28, volatility: 0.6, baseVolume: 22_000_000_000, allocationPct: 11 },
  { id: 'BONDS_US30Y', category: CATEGORIES.BONDS, ticker: 'US30Y', name: 'US 30-Year Treasury', price: 4.45, volatility: 0.45, baseVolume: 9_000_000_000, allocationPct: 4 },
  { id: 'BONDS_OTHERS', category: CATEGORIES.BONDS, ticker: 'OTHERS', name: 'EU / JGB / Corp / EM', price: 3.98, volatility: 0.4, baseVolume: 26_000_000_000, allocationPct: 77 },

  { id: 'COMMODITIES_GOLD', category: CATEGORIES.COMMODITIES, ticker: 'GOLD', name: 'Gold Spot (XAU/USD)', price: 2415.6, volatility: 0.3, baseVolume: 15_000_000_000, allocationPct: 70.3 },
  { id: 'COMMODITIES_SILVER', category: CATEGORIES.COMMODITIES, ticker: 'SILVER', name: 'Silver Spot (XAG/USD)', price: 30.85, volatility: 0.5, baseVolume: 4_000_000_000, allocationPct: 8.1 },
  { id: 'COMMODITIES_OIL', category: CATEGORIES.COMMODITIES, ticker: 'OIL', name: 'Crude Oil WTI', price: 78.4, volatility: 0.6, baseVolume: 9_500_000_000, allocationPct: 21.6 },

  { id: 'CRYPTO_BTC', category: CATEGORIES.CRYPTO, ticker: 'BTC', name: 'Bitcoin', price: 96500, volatility: 1.2, baseVolume: 28_000_000_000, tier: CRYPTO_TIERS.BIG_CAP },
  { id: 'CRYPTO_ETH', category: CATEGORIES.CRYPTO, ticker: 'ETH', name: 'Ethereum', price: 3350, volatility: 1.6, baseVolume: 14_000_000_000, tier: CRYPTO_TIERS.BIG_CAP },
  { id: 'CRYPTO_SOL', category: CATEGORIES.CRYPTO, ticker: 'SOL', name: 'Solana', price: 148.2, volatility: 2.2, baseVolume: 3_200_000_000, tier: CRYPTO_TIERS.BIG_CAP },
  { id: 'CRYPTO_BNB', category: CATEGORIES.CRYPTO, ticker: 'BNB', name: 'BNB', price: 615.4, volatility: 1.8, baseVolume: 1_800_000_000, tier: CRYPTO_TIERS.BIG_CAP },

  { id: 'CRYPTO_AAVE', category: CATEGORIES.CRYPTO, ticker: 'AAVE', name: 'Aave', price: 85.5, volatility: 3.5, baseVolume: 210_000_000, tier: CRYPTO_TIERS.MID_CAP },
  { id: 'CRYPTO_LINK', category: CATEGORIES.CRYPTO, ticker: 'LINK', name: 'Chainlink', price: 14.7, volatility: 3.0, baseVolume: 350_000_000, tier: CRYPTO_TIERS.MID_CAP },
  { id: 'CRYPTO_ARB', category: CATEGORIES.CRYPTO, ticker: 'ARB', name: 'Arbitrum', price: 0.62, volatility: 4.0, baseVolume: 90_000_000, tier: CRYPTO_TIERS.MID_CAP },
  { id: 'CRYPTO_NEAR', category: CATEGORIES.CRYPTO, ticker: 'NEAR', name: 'NEAR Protocol', price: 4.85, volatility: 3.2, baseVolume: 120_000_000, tier: CRYPTO_TIERS.MID_CAP },

  { id: 'CRYPTO_DOGE', category: CATEGORIES.CRYPTO, ticker: 'DOGE', name: 'Dogecoin', price: 0.182, volatility: 3.8, baseVolume: 1_100_000_000, tier: CRYPTO_TIERS.MEME },
  { id: 'CRYPTO_PEPE', category: CATEGORIES.CRYPTO, ticker: '1000PEPE', name: 'Pepe', price: 0.0091, volatility: 5.5, baseVolume: 300_000_000, tier: CRYPTO_TIERS.MEME },
  { id: 'CRYPTO_HMSTR', category: CATEGORIES.CRYPTO, ticker: 'HMSTR', name: 'Hamster Kombat', price: 0.0021, volatility: 6.0, baseVolume: 60_000_000, tier: CRYPTO_TIERS.MEME },
  { id: 'CRYPTO_VANRY', category: CATEGORIES.CRYPTO, ticker: 'VANRY', name: 'Vanar Chain', price: 0.048, volatility: 5.0, baseVolume: 25_000_000, tier: CRYPTO_TIERS.MEME }
];

const ASSET_CLASS_ORDER = [
  { id: CATEGORIES.STOCKS, label: 'Stocks' },
  { id: CATEGORIES.BONDS, label: 'Bonds' },
  { id: CATEGORIES.COMMODITIES, label: 'Commodities' },
  { id: CATEGORIES.CRYPTO, label: 'Crypto' }
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
      reverse_repo: 412.8, // $B outstanding
      qe_qt_status: 'QT'
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
      reverse_repo: round(Math.max(this.globalLiquidity.reverse_repo + randomBetween(-8, 8), 0), 2),
      qe_qt_status: this.globalLiquidity.qe_qt_status
    };
  }

  /** Builds the API/websocket payload for the liquidity flow map UI. */
  getSnapshot() {
    const payloads = this.assets.map((asset) => this._toPayload(asset));
    const byCategory = (category) => payloads.filter((a) => a.category === category);

    const currencies = byCategory(CATEGORIES.CURRENCY);
    const cryptoAssets = byCategory(CATEGORIES.CRYPTO);

    const assetClasses = ASSET_CLASS_ORDER.map(({ id, label }) => {
      const allChildren = byCategory(id);
      // CRYPTO has ~3x the constituents of the other classes; the flow map
      // node only shows the big-cap movers, full detail lives in the
      // Top Altcoins by Flow board below.
      const children = id === CATEGORIES.CRYPTO ? allChildren.filter((a) => a.tier === CRYPTO_TIERS.BIG_CAP) : allChildren;
      const flowAmount = allChildren.reduce((sum, child) => sum + child.flow_amount, 0);
      return {
        id,
        label,
        flow_amount: Math.round(flowAmount),
        flow_status: flowAmount > 0 ? 'IN' : flowAmount < 0 ? 'OUT' : 'NEUTRAL',
        children
      };
    });

    const cryptoByTier = Object.values(CRYPTO_TIERS).reduce((acc, tier) => {
      acc[tier] = cryptoAssets.filter((a) => a.tier === tier);
      return acc;
    }, {});

    return {
      timestamp: new Date().toISOString(),
      global_liquidity: { ...this.globalLiquidity },
      currencies,
      asset_classes: assetClasses,
      crypto_by_tier: cryptoByTier,
      alerts: this._buildAlerts(currencies, assetClasses)
    };
  }

  _buildAlerts(currencies, assetClasses) {
    const netFlow6h = assetClasses.reduce((sum, c) => sum + c.flow_amount, 0);

    const biggestOutflowCcy = [...currencies].sort((a, b) => a.flow_amount - b.flow_amount)[0];
    const sortedClasses = [...assetClasses].sort((a, b) => a.flow_amount - b.flow_amount);
    const biggestOutflowClass = sortedClasses[0];
    const biggestInflowClass = sortedClasses[sortedClasses.length - 1];

    return [
      `NET FLOW (6H): ${netFlow6h >= 0 ? '+' : ''}$${(netFlow6h / 1_000_000_000).toFixed(1)}B`,
      biggestOutflowCcy
        ? `OUTFLOW TERBESAR: ${biggestOutflowCcy.ticker} ZONE ${(biggestOutflowCcy.flow_amount / 1_000_000_000).toFixed(1)}B`
        : null,
      biggestOutflowClass && biggestInflowClass && biggestOutflowClass.id !== biggestInflowClass.id
        ? `ROTASI: ${biggestOutflowClass.label} → ${biggestInflowClass.label}`
        : null
    ].filter(Boolean);
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
      flow_amount: Math.round(flowAmount),
      allocation_pct: asset.allocationPct,
      tier: asset.tier,
      accent: asset.accent
    };
  }
}

module.exports = { MarketDataService, CATEGORIES, CRYPTO_TIERS };
