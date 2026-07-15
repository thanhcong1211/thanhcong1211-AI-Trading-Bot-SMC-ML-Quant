'use client';

import { useEffect, useMemo, useState } from 'react';
import { GlobalLiquidityBar } from '@/components/GlobalLiquidityBar';
import { DashboardColumn } from '@/components/DashboardColumn';
import { AssetTable } from '@/components/AssetTable';
import { getApiBaseUrl, getSocket } from '@/lib/socket';
import { MarketFlowSnapshot } from '@/lib/types';

type ConnectionStatus = 'connecting' | 'live' | 'offline';

const DEFAULT_LIQUIDITY = { fed_balance: 0, m2_growth: 0, reverse_repo: 0 };

export default function DashboardPage() {
  const [snapshot, setSnapshot] = useState<MarketFlowSnapshot | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');

  useEffect(() => {
    let cancelled = false;

    fetch(`${getApiBaseUrl()}/api/v1/market-flow`)
      .then((res) => res.json())
      .then((data: MarketFlowSnapshot) => {
        if (!cancelled) setSnapshot(data);
      })
      .catch(() => {
        /* socket connection below will retry; REST is only a fast first paint */
      });

    const socket = getSocket();

    const handleSnapshot = (data: MarketFlowSnapshot) => setSnapshot(data);
    const handleConnect = () => setConnectionStatus('live');
    const handleDisconnect = () => setConnectionStatus('offline');
    const handleConnecting = () => setConnectionStatus('connecting');

    socket.on('connect', handleConnect);
    socket.on('disconnect', handleDisconnect);
    socket.io.on('reconnect_attempt', handleConnecting);
    socket.on('market-flow:snapshot', handleSnapshot);
    socket.on('market-flow:update', handleSnapshot);

    return () => {
      cancelled = true;
      socket.off('connect', handleConnect);
      socket.off('disconnect', handleDisconnect);
      socket.io.off('reconnect_attempt', handleConnecting);
      socket.off('market-flow:snapshot', handleSnapshot);
      socket.off('market-flow:update', handleSnapshot);
    };
  }, []);

  const assetsByCategory = useMemo(() => {
    const assets = snapshot?.assets ?? [];
    return {
      forex: assets.filter((a) => a.category === 'FOREX'),
      stocks: assets.filter((a) => a.category === 'STOCKS'),
      bonds: assets.filter((a) => a.category === 'BONDS'),
      commodities: assets.filter((a) => a.category === 'COMMODITIES'),
      crypto: assets.filter((a) => a.category === 'CRYPTO')
    };
  }, [snapshot]);

  return (
    <main className="flex min-h-screen flex-col">
      <GlobalLiquidityBar
        liquidity={snapshot?.global_liquidity ?? DEFAULT_LIQUIDITY}
        timestamp={snapshot?.timestamp ?? null}
        connectionStatus={connectionStatus}
      />

      <div className="grid flex-1 grid-cols-1 gap-3 p-3 md:grid-cols-3">
        <DashboardColumn title="Currency & Macro">
          <AssetTable title="Forex" assets={assetsByCategory.forex} />
        </DashboardColumn>

        <DashboardColumn title="Main Asset Flow">
          <AssetTable title="Stocks" assets={assetsByCategory.stocks} />
          <AssetTable title="Bonds" assets={assetsByCategory.bonds} />
          <AssetTable title="Commodities" assets={assetsByCategory.commodities} />
        </DashboardColumn>

        <DashboardColumn title="Altcoins / Mid-cap">
          <AssetTable title="Crypto" assets={assetsByCategory.crypto} />
        </DashboardColumn>
      </div>

      {!snapshot && (
        <div className="p-6 text-center text-sm text-terminal-neutral">Connecting to market feed…</div>
      )}
    </main>
  );
}
