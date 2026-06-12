"""
Feature engineering and technical indicator calculation.
All functions operate on a DataFrame with at minimum a 'Close' column.
"""

import pandas as pd
import numpy as np


# ── Oscillators / Momentum ────────────────────────────────────────────────────

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI using exponential moving average for smoothing."""
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd       = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    histogram  = macd - macd_signal
    return macd, macd_signal, histogram


def calculate_bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    """Returns (upper_band, middle_band, lower_band)."""
    mid   = series.rolling(window=window).mean()
    std   = series.rolling(window=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high_low  = df["High"] - df["Low"]
    high_prev = (df["High"] - df["Close"].shift()).abs()
    low_prev  = (df["Low"]  - df["Close"].shift()).abs()
    tr  = pd.concat([high_low, high_prev, low_prev], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    """Stochastic oscillator — returns (%K, %D)."""
    lowest_low   = df["Low"].rolling(k_period).min()
    highest_high = df["High"].rolling(k_period).max()
    k = 100 * (df["Close"] - lowest_low) / (highest_high - lowest_low + 1e-9)
    d = k.rolling(d_period).mean()
    return k, d


# ── Add All Features to DataFrame ─────────────────────────────────────────────

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches a stock DataFrame with a comprehensive set of technical indicators.

    Input columns required: Close (High, Low optional for ATR / Stochastic).
    Returns a copy of the DataFrame with new feature columns.
    """
    df = df.copy()
    close = df["Close"]

    # Moving averages
    df["SMA_10"]  = close.rolling(10).mean()
    df["SMA_20"]  = close.rolling(20).mean()
    df["SMA_50"]  = close.rolling(50).mean()
    df["SMA_200"] = close.rolling(200).mean()
    df["EMA_12"]  = close.ewm(span=12, adjust=False).mean()
    df["EMA_26"]  = close.ewm(span=26, adjust=False).mean()

    # MACD family
    df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = calculate_macd(close)

    # RSI
    df["RSI"] = calculate_rsi(close)

    # Bollinger Bands
    df["BB_Upper"], df["BB_Mid"], df["BB_Lower"] = calculate_bollinger_bands(close)
    df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Mid"]
    df["BB_Pct"]   = (close - df["BB_Lower"]) / (df["BB_Upper"] - df["BB_Lower"] + 1e-9)

    # Momentum / returns
    df["Return_1d"]  = close.pct_change(1)
    df["Return_5d"]  = close.pct_change(5)
    df["Return_20d"] = close.pct_change(20)

    # Volatility
    df["Volatility_20"] = df["Return_1d"].rolling(20).std()

    # Volume features (if present)
    if "Volume" in df.columns:
        df["Volume_MA_20"]   = df["Volume"].rolling(20).mean()
        df["Volume_Ratio"]   = df["Volume"] / df["Volume_MA_20"].replace(0, np.nan)

    # ATR and Stochastic (need High / Low)
    if "High" in df.columns and "Low" in df.columns:
        df["ATR"] = calculate_atr(df)
        df["Stoch_K"], df["Stoch_D"] = calculate_stochastic(df)

    # Cross-over signals
    df["Golden_Cross"] = (df["SMA_50"] > df["SMA_200"]).astype(int)  # 1 = bullish
    df["Price_Above_SMA20"] = (close > df["SMA_20"]).astype(int)

    return df
