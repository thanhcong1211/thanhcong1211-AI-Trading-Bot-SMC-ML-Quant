"""
Utility Helper Functions
Various utility functions for the trading system
"""

import os
import json
import time
import logging
import unicodedata

logger = logging.getLogger(__name__)

# Global language for logs/notifications. Values: 'en' or 'vi'
LOG_LANG = 'en'

# Simple translation dictionary for frequently used messages
TRANSLATIONS = {
    "Pattern classifier training completed": "✅ Huấn luyện bộ phân loại mô hình hoàn tất",
    "Pattern classifier training failed": "❌ Huấn luyện bộ phân loại mô hình thất bại",
    "--train-patterns requested: Generating dataset and training pattern classifier...": "📚 Yêu cầu --train-patterns: Đang sinh dữ liệu và huấn luyện bộ phân loại mô hình...",
    "ML libraries not available in this environment. Install scikit-learn/xgboost/joblib.": "❌ Thư viện ML chưa được cài đặt. Hãy cài scikit-learn và joblib.",
    "Generating synthetic dataset ({samples} samples/pattern) ...": "📦 Đang sinh dữ liệu tổng hợp ({samples} mẫu/loại) ...",
    "Loading dataset from {path} ...": "📥 Đang tải dữ liệu từ {path} ...",
    "Training RandomForest classifier on synthetic patterns...": "🧠 Đang huấn luyện RandomForest trên các mẫu mô hình...",
    "Saved classifier: {path}": "✅ Đã lưu bộ phân loại: {path}",
    "Saved scaler: {path}": "✅ Đã lưu scaler: {path}",
}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol names to base instrument names.

    Examples:
      - 'XAUUSD-VIPc' -> 'XAUUSD'
      - 'XAUUSDm' -> 'XAUUSD'
      - 'GOLD' -> 'XAUUSD' (alias)
    """
    if symbol is None:
        return symbol
    s = symbol.upper()
    # Common VT/other broker variants mapping
    variants = [
        'XAUUSC', 'XAUUSDC', 'XAUUSD-C', 'XAUUSD.C', 'XAUUSDVIPC', 'XAUUSD-VIPC', 'XAUUSDM', 'XAUUSDM'
    ]
    for v in variants:
        if v in s:
            return 'XAUUSD'

    # Map common precious metals aliases
    if 'XAU' in s or 'GOLD' in s:
        return 'XAUUSD'
    # Map common crypto aliases (BTC / XBT) to broker pair
    if 'BTC' in s or 'XBT' in s:
        return 'BTCUSD'
    return symbol


def tr(msg: str, **kwargs) -> str:
    """Translate a message key to the selected language if available.

    This is deliberately simple: only translates exact keys present in TRANSLATIONS.
    Use `tr("Saved classifier: {path}", path=p)` to format translated templates.
    """
    try:
        if LOG_LANG == 'vi':
            tmpl = TRANSLATIONS.get(msg, None)
            if tmpl is not None:
                return tmpl.format(**kwargs)
        return msg.format(**kwargs) if kwargs else msg
    except Exception:
        return msg


def remove_accents(text: str) -> str:
    """Remove diacritics from Unicode text, return ASCII-friendly string."""
    try:
        if not isinstance(text, str):
            return text
        nk = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in nk if not unicodedata.combining(c)])
    except Exception:
        return text


def _persist_latest_signal_log(signal: dict):
    """Append a JSON line with the latest signal into `live_trading/logs/latest_signals.jsonl`.

    This is a lightweight best-effort logger used for debugging and diagnostics.
    It will attempt to make all values JSON-serializable and preserve `fusion_reasons`.

    Additionally, if `fusion_reasons` is present, persist it separately into
    `fusion_explains.jsonl` to guarantee explainability artifacts are captured
    even if the main signal path mutates or strips them later.
    """
    try:
        log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        out_path = os.path.join(log_dir, 'latest_signals.jsonl')

        # Make a JSON-serializable copy
        serial = {}
        for k, v in (signal or {}).items():
            try:
                if hasattr(v, 'item'):
                    serial[k] = v.item()
                elif isinstance(v, (int, float, str, bool)) or v is None:
                    serial[k] = v
                else:
                    # Try json.dumps first for nested dict/list
                    try:
                        json.dumps(v)
                        serial[k] = v
                    except Exception:
                        serial[k] = str(v)
            except Exception:
                try:
                    serial[k] = str(v)
                except Exception:
                    serial[k] = None

        # Ensure timestamp for ordering
        try:
            serial.setdefault('persist_ts', int(time.time() * 1000))
        except Exception:
            serial['persist_ts'] = None

        # Append as JSON line (UTF-8, keep unicode for readability)
        try:
            with open(out_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(serial, ensure_ascii=False) + '\n')
        except Exception:
            # Fallback: ascii-safe write
            try:
                with open(out_path, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps(serial, ensure_ascii=True) + '\n')
            except Exception as e:
                logger.debug(f"⚠️ _persist_latest_signal_log failed to write: {e}")

        # If fusion_reasons present, persist to dedicated explains file as well
        try:
            fusion = serial.get('fusion_reasons') or (signal or {}).get('fusion_reasons')
            if fusion:
                fusion_file = os.path.join(log_dir, 'fusion_explains.jsonl')
                payload = {
                    'signal_id': serial.get('signal_id'),
                    'timestamp': serial.get('timestamp') or serial.get('persist_ts'),
                    'fusion_reasons': fusion
                }
                try:
                    with open(fusion_file, 'a', encoding='utf-8') as fh2:
                        fh2.write(json.dumps(payload, ensure_ascii=False) + '\n')
                except Exception:
                    try:
                        with open(fusion_file, 'a', encoding='utf-8') as fh2:
                            fh2.write(json.dumps(payload, ensure_ascii=True) + '\n')
                    except Exception as e:
                        logger.debug(f"⚠️ Failed writing fusion_explains: {e}")
        except Exception:
            # Non-critical: continue
            pass

    except Exception as e:
        try:
            logger.debug(f"⚠️ _persist_latest_signal_log error: {e}")
        except Exception:
            pass


def _log_separator(msg: str = None, char: str = '=', width: int = 80):
    """Helper: pretty separator for log blocks.
    
    Call `logger.sep("Optional message")` to print a clear visual separator in logs
    so new commands/blocks are easy to spot.
    """
    try:
        line = char * width
        logger.info(line)
        if msg:
            logger.info(f" {msg} ")
            logger.info(line)
        else:
            logger.info(line)
    except Exception:
        # Best-effort: avoid raising from logging helper
        try:
            print('=' * width)
            if msg:
                print(msg)
            print('=' * width)
        except Exception:
            pass


def save_feature_importances(model, feature_cols, model_name: str, 
                            outdir: str = 'live_trading/feature_importances', 
                            top_k: int = 20,
                            X=None, y=None, 
                            compute_permutation: bool = False, 
                            n_repeats: int = 10, 
                            random_state: int = 42):
    """Compute and save feature importances for trained models.

    Supports models with `feature_importances_`, `coef_`, or XGBoost `get_booster()`.
    Saves CSV to `outdir/{model_name}_feature_importances.csv` and logs top-k features.
    """
    try:
        os.makedirs(outdir, exist_ok=True)
        import numpy as np
        import pandas as pd

        # Compute importances array aligned with feature_cols (base importance)
        if hasattr(model, 'feature_importances_'):
            importances = np.array(model.feature_importances_)
        elif hasattr(model, 'coef_'):
            coef = np.array(model.coef_)
            if coef.ndim > 1:
                importances = np.mean(np.abs(coef), axis=0)
            else:
                importances = np.abs(coef)
        elif hasattr(model, 'get_booster'):
            try:
                booster = model.get_booster()
                score = booster.get_score(importance_type='gain')
                importances = np.zeros(len(feature_cols))
                for i, f in enumerate(feature_cols):
                    importances[i] = float(score.get(f, score.get(f'f{i}', 0.0)))
            except Exception:
                importances = np.zeros(len(feature_cols))
        else:
            importances = np.zeros(len(feature_cols))

        # Ensure length matches
        if len(importances) != len(feature_cols):
            arr = np.zeros(len(feature_cols))
            arr[:min(len(importances), len(arr))] = importances[:len(arr)]
            importances = arr

        df_imp = pd.DataFrame({'feature': list(feature_cols), 'importance': list(importances)})
        df_imp = df_imp.sort_values('importance', ascending=False).reset_index(drop=True)

        csv_path = os.path.join(outdir, f"{model_name}_feature_importances.csv")
        try:
            df_imp.to_csv(csv_path, index=False, encoding='utf-8')
            logger.info(f"✅ Đã lưu feature importances cho {model_name} → {csv_path}")
        except Exception:
            logger.debug(f"⚠️ Không thể lưu feature importances cho {model_name} vào {csv_path}")

        # Also produce a PNG bar chart for top_k features if matplotlib is available
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            top = df_imp.head(top_k)
            plt.figure(figsize=(10, 6))
            plt.barh(top['feature'], top['importance'])
            plt.xlabel('Importance')
            plt.title(f'Top {top_k} Feature Importances: {model_name}')
            plt.gca().invert_yaxis()
            plt.tight_layout()
            png_path = os.path.join(outdir, f"{model_name}_feature_importances.png")
            plt.savefig(png_path, dpi=150)
            plt.close()
            logger.debug(f"✅ Saved feature importance chart: {png_path}")
        except Exception:
            pass

        # Log top features
        logger.info(f"🔝 Top {min(top_k, len(df_imp))} features for {model_name}:")
        for idx, row in df_imp.head(top_k).iterrows():
            logger.info(f"  {idx+1}. {row['feature']}: {row['importance']:.4f}")

        # Optionally compute permutation importance if X, y provided
        if compute_permutation and X is not None and y is not None:
            try:
                from sklearn.inspection import permutation_importance
                perm_result = permutation_importance(
                    model, X, y, 
                    n_repeats=n_repeats, 
                    random_state=random_state,
                    n_jobs=-1
                )
                perm_imp = perm_result.importances_mean
                df_perm = pd.DataFrame({
                    'feature': list(feature_cols),
                    'perm_importance': list(perm_imp)
                })
                df_perm = df_perm.sort_values('perm_importance', ascending=False).reset_index(drop=True)
                
                perm_csv = os.path.join(outdir, f"{model_name}_permutation_importance.csv")
                df_perm.to_csv(perm_csv, index=False, encoding='utf-8')
                logger.info(f"✅ Saved permutation importance: {perm_csv}")
                
                logger.info(f"🔝 Top {min(top_k, len(df_perm))} permutation features:")
                for idx, row in df_perm.head(top_k).iterrows():
                    logger.info(f"  {idx+1}. {row['feature']}: {row['perm_importance']:.4f}")
            except Exception as e:
                logger.debug(f"⚠️ Permutation importance computation failed: {e}")

    except Exception as e:
        logger.warning(f"⚠️ save_feature_importances failed: {e}")


def add_session_features(df, tz_offset_hours: int = 0):
    """Add trading session features to dataframe.
    
    Args:
        df: DataFrame with 'time' column (datetime)
        tz_offset_hours: Timezone offset from UTC (e.g., 7 for Asia/Bangkok)
        
    Returns:
        DataFrame with added session features
    """
    try:
        import pandas as pd
        
        df = df.copy()
        
        # Ensure time column is datetime
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            
            # Apply timezone offset
            df['local_time'] = df['time'] + pd.Timedelta(hours=tz_offset_hours)
            
            # Extract hour
            df['hour'] = df['local_time'].dt.hour
            
            # Define sessions
            df['session_asian'] = ((df['hour'] >= 0) & (df['hour'] < 9)).astype(int)
            df['session_london'] = ((df['hour'] >= 9) & (df['hour'] < 17)).astype(int)
            df['session_ny'] = ((df['hour'] >= 14) & (df['hour'] < 22)).astype(int)
            df['session_overlap'] = ((df['hour'] >= 14) & (df['hour'] < 17)).astype(int)
            
            # Weekday (0=Monday, 6=Sunday)
            df['weekday'] = df['local_time'].dt.dayofweek
            
            # Is weekend
            df['is_weekend'] = (df['weekday'] >= 5).astype(int)
            
        return df
        
    except Exception as e:
        logger.warning(f"⚠️ add_session_features failed: {e}")
        return df
