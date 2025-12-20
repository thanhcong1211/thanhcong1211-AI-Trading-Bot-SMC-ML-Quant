import json
import sys, os
# Ensure parent 'live_trading' folder is on sys.path so local imports work when running from tools/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.complete_ai_trading_system import MarketDataFetcher, TechnicalIndicators, add_session_features


def analyze(symbol=None, days=90, future_bars=3):
    try:
        fetcher = MarketDataFetcher(symbol=symbol or None)
        bars = int(days * 24)
        df = fetcher.fetch_mt5_data(symbol=fetcher.symbol if symbol is None else symbol, timeframe=None, bars=bars)
        if df is None or df.empty:
            return {'ok': False, 'error': 'no_data', 'symbol': fetcher.symbol}

        df = TechnicalIndicators.calculate_atr(df.copy(), period=14)
        df = TechnicalIndicators.analyze_trend(df)
        df = add_session_features(df)
        df['future_close'] = df['close'].shift(-future_bars)
        df['future_move'] = df['future_close'] - df['close']
        df['range'] = df['high'] - df['low']

        sessions = {1: 'asia', 2: 'eu', 3: 'us', 0: 'other'}
        results = {}
        for code, label in sessions.items():
            if 'session' in df.columns:
                sub = df[df['session'] == int(code)]
            elif f'session_{label}' in df.columns:
                sub = df[df[f'session_{label}'] == 1]
            else:
                sub = df.copy()

            if sub is None or len(sub) < 30:
                results[label] = {'count': 0}
                continue

            avg_range = float(sub['range'].mean())
            avg_atr = float(sub['atr'].mean()) if 'atr' in sub.columns else float(sub['range'].mean())
            trend_quality = float(sub['trend_quality'].mean()) if 'trend_quality' in sub.columns else 0.0
            percent_trending = float((sub['is_sideways'] == 0).mean()) if 'is_sideways' in sub.columns else 0.0
            future_mean = float(sub['future_move'].mean())
            future_std = float(sub['future_move'].std())
            prob_direction = float((sub['future_move'] > 0).mean())

            tp_conservative = avg_range * 0.5
            tp_aggressive = avg_range * 1.5
            sl_base = avg_atr
            if avg_range < avg_atr * 0.8:
                sl_suggest = max(0.5 * avg_atr, avg_range * 0.5)
            else:
                sl_suggest = sl_base

            if trend_quality >= 0.8 and percent_trending > 0.6:
                style = 'trend'
                recommended_tp = max(tp_aggressive, abs(future_mean))
                recommended_sl = sl_suggest * 1.0
            elif avg_range < avg_atr * 0.8:
                style = 'low_vol_scalp'
                recommended_tp = max(0.5, tp_conservative)
                recommended_sl = max(0.5, sl_suggest * 0.8)
            else:
                style = 'balanced'
                recommended_tp = max(tp_conservative, abs(future_mean))
                recommended_sl = sl_suggest

            lot_multiplier = min(1.0, max(0.1, 0.3 + trend_quality * 0.7 - (future_std / (avg_range + 1e-6)) * 0.2))

            results[label] = {
                'count': len(sub),
                'avg_range': round(avg_range, 5),
                'avg_atr': round(avg_atr, 5),
                'trend_quality': round(trend_quality, 3),
                'percent_trending': round(percent_trending, 3),
                'future_mean': round(future_mean, 5),
                'future_std': round(future_std, 5),
                'prob_future_up': round(prob_direction, 3),
                'style': style,
                'recommended_tp_price': round(recommended_tp, 5),
                'recommended_sl_price': round(recommended_sl, 5),
                'recommended_tp_atr_mult': round(recommended_tp / (avg_atr + 1e-9), 2) if avg_atr > 0 else None,
                'recommended_sl_atr_mult': round(recommended_sl / (avg_atr + 1e-9), 2) if avg_atr > 0 else None,
                'lot_multiplier_of_base': round(lot_multiplier, 3)
            }

        scores = {}
        for k, v in results.items():
            if v.get('count', 0) == 0:
                scores[k] = -999
                continue
            score = v['trend_quality'] * 2.0 + v['percent_trending'] * 1.5 - (v['future_std'] / (v['avg_range'] + 1e-9))
            scores[k] = score

        best_session = max(scores.items(), key=lambda x: x[1])[0]
        return {'ok': True, 'symbol': fetcher.symbol, 'days': days, 'best_session': best_session, 'scores': scores, 'results': results}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


if __name__ == '__main__':
    # Default to auto-detect broker symbol for GOLD (do not force XAUUSD)
    out = analyze(symbol=None, days=90, future_bars=3)
    print(json.dumps(out, indent=2, ensure_ascii=False))
