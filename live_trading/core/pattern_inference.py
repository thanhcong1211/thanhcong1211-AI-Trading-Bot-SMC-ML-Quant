import os
import pandas as pd
import numpy as np
import joblib
from typing import Tuple, Optional


def load_pattern_model(model_dir: str):
    """Load classifier and scaler from a model directory.
    Expects files `pattern_classifier.pkl` and `pattern_scaler.pkl` (joblib/pickle).
    Returns (model, scaler)
    """
    model_path = os.path.join(model_dir, 'pattern_classifier.pkl')
    scaler_path = os.path.join(model_dir, 'pattern_scaler.pkl')
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")
    model = joblib.load(model_path)
    scaler = None
    if os.path.exists(scaler_path):
        try:
            scaler = joblib.load(scaler_path)
        except Exception:
            scaler = None
    return model, scaler


def aggregate_features_from_window(df_window: pd.DataFrame) -> dict:
    """Compute simple aggregated features used by the training baseline.

    Features:
      - mean_return, std_return, last_return
      - mean_volume
      - mean_range (high-low)/open
      - volatility (std of returns)
    """
    try:
        close = df_window['close'].values
        # returns between consecutive closes
        returns = np.diff(close) / (close[:-1] + 1e-8)
        mean_return = np.nanmean(returns) if len(returns) > 0 else 0.0
        std_return = np.nanstd(returns) if len(returns) > 0 else 0.0
        max_return = float(np.nanmax(returns)) if len(returns) > 0 else 0.0
        min_return = float(np.nanmin(returns)) if len(returns) > 0 else 0.0
        last_return = float(returns[-1]) if len(returns) > 0 else 0.0
        vol_mean = float(df_window['volume'].mean()) if 'volume' in df_window.columns else 0.0
        range_mean = float(((df_window['high'] - df_window['low']) / (df_window['close'] + 1e-8)).mean())
        features = {
            'mean_return': float(mean_return),
            'std_return': float(std_return),
            'max_return': float(max_return),
            'min_return': float(min_return),
            'last_return': float(last_return),
            'vol_mean': float(vol_mean),
            'range_mean': float(range_mean)
        }
        return features
    except Exception:
        return {
            'mean_return': 0.0,
            'std_return': 0.0,
            'last_return': 0.0,
            'mean_volume': 0.0,
            'mean_range': 0.0,
            'volatility': 0.0
        }


def compute_feature_matrix(df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """Slide a window across `df` and compute aggregated features for each window end.
    Returns a DataFrame indexed by the window end timestamp with feature columns.
    """
    feats = []
    idx = []
    if len(df) < window:
        return pd.DataFrame()
    for i in range(window, len(df) + 1):
        w = df.iloc[i-window:i]
        f = aggregate_features_from_window(w)
        feats.append(f)
        idx.append(df.index[i-1])
    X = pd.DataFrame(feats, index=idx)
    return X


def predict_on_df(df: pd.DataFrame, model, scaler=None, window: int = 30) -> pd.DataFrame:
    """Compute features and return prediction probabilities and top label per timestamp.

    Returns DataFrame with columns: `top_pattern`, `top_prob`, and probability columns for each class.
    The index corresponds to the window end timestamps.
    """
    X = compute_feature_matrix(df, window=window)
    if X.empty:
        return pd.DataFrame()
    # Apply scaler if given
    X_in = X.values
    if scaler is not None:
        try:
            X_in = scaler.transform(X_in)
        except Exception:
            pass
    # Predict probabilities if supported
    try:
        probs = model.predict_proba(X_in)
        classes = list(model.classes_)
        probs_df = pd.DataFrame(probs, index=X.index, columns=[f'prob_{c}' for c in classes])
        probs_df['top_pattern'] = probs_df.idxmax(axis=1).str.replace('prob_', '')
        probs_df['top_prob'] = probs_df.max(axis=1)
        # normalize column order
        cols = ['top_pattern', 'top_prob'] + [c for c in probs_df.columns if c.startswith('prob_')]
        return probs_df[cols]
    except Exception:
        # Fallback to predict (no probs)
        preds = model.predict(X_in)
        df_out = pd.DataFrame({'top_pattern': preds, 'top_prob': 1.0}, index=X.index)
        return df_out
