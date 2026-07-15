'use client';

import { useEffect, useMemo, useState } from 'react';
import { GlobalLiquidityBar } from '@/components/GlobalLiquidityBar';
import { LiquidityHero } from '@/components/LiquidityHero';
import { CurrencyLiquidityRow } from '@/components/CurrencyLiquidityRow';
import { FlowMapDiagram } from '@/components/FlowMapDiagram';
import { AltcoinFlowBoard } from '@/components/AltcoinFlowBoard';
import { BottomTicker } from '@/components/BottomTicker';
import { getApiBaseUrl, getSocket } from '@/lib/socket';
import { CryptoTier, MarketFlowSnapshot } from '@/lib/types';

type ConnectionStatus = 'connecting' | 'live' | 'offline';

const DEFAULT_LIQUIDITY = { fed_balance: 0, m2_growth: 0, reverse_repo: 0, qe_qt_status: 'QT' };
const EMPTY_TIERS: Record<CryptoTier, never[]> = { BIG_CAP: [], MID_CAP: [], MEME: [] };

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

  const alerts = useMemo(() => snapshot?.alerts ?? [], [snapshot]);

  return (
    <main className="flex min-h-screen flex-col">
      <GlobalLiquidityBar timestamp={snapshot?.timestamp ?? null} connectionStatus={connectionStatus} />

      <div className="flex-1 pb-12">
        <LiquidityHero liquidity={snapshot?.global_liquidity ?? DEFAULT_LIQUIDITY} />
        <CurrencyLiquidityRow currencies={snapshot?.currencies ?? []} />
        <FlowMapDiagram assetClasses={snapshot?.asset_classes ?? []} />
        <AltcoinFlowBoard cryptoByTier={snapshot?.crypto_by_tier ?? EMPTY_TIERS} />
      </div>

      <BottomTicker alerts={alerts} />

      {!snapshot && (
        <div className="p-6 text-center text-sm text-terminal-neutral">Connecting to market feed…</div>
      )}
    </main>
  );
}
