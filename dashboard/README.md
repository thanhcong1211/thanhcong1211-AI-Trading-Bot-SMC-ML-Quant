# Global Liquidity & Asset Flow Dashboard

Cyber-terminal style real-time dashboard for macro liquidity and cross-asset
net flow, per the project spec. Two services:

- `backend/` — Express + Socket.io API. Simulates the Asset Flow Engine
  (`flow_amount = (current_price - previous_price) * volume`) with a mock
  market feed so the UI can be built/demoed before a real data vendor is
  wired in. Redis caching is optional (set `REDIS_URL`); the service runs
  fine without it.
- `frontend/` — Next.js (App Router) + Tailwind CSS + Framer Motion UI.
  Connects over WebSocket for live ticks, with a REST fetch for first paint.

## Run locally

```bash
# backend
cd backend
cp .env.example .env
npm install
npm run dev   # http://localhost:4000

# frontend (separate terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev   # http://localhost:3000
```

## API

`GET /api/v1/market-flow` returns the current snapshot. The same shape is
pushed over Socket.io as `market-flow:snapshot` (on connect) and
`market-flow:update` (every tick, default every 2s).

## Swapping in real data

Replace `MarketDataService.tick()` in `backend/src/marketDataService.js`
with calls to your real market data / FRED (Fed balance sheet, M2, reverse
repo) and pricing providers, writing new `price`/`lastVolume` values before
`getSnapshot()` recomputes flow. The API contract and frontend do not need
to change.
