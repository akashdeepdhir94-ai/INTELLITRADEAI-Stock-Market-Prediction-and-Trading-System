"""
AI Prediction API
─────────────────
GET /api/v1/predict/{symbol}  — composite signal with confidence breakdown
"""

import logging
from typing import Optional

import numpy as np
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from utils.feature_engineering import add_features

import math
from typing import Any

def _sanitize(value: Any) -> Any:
    """Recursively replace NaN/inf with None so JSON serialization never fails."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value

logger = logging.getLogger("intellitrade.predict")
router = APIRouter()


# ── Signal Engine ─────────────────────────────────────────────────────────────

def _trend_signal(row: dict) -> tuple[str, float]:
    """MA crossover + price position — returns (signal, confidence 0–1)."""
    sma20  = row.get("SMA_20",  np.nan)
    sma50  = row.get("SMA_50",  np.nan)
    sma200 = row.get("SMA_200", np.nan)
    price  = row["Close"]

    if any(np.isnan(v) for v in [sma20, sma50, sma200]):
        return "HOLD", 0.5

    bulls = sum([
        price > sma20,
        price > sma50,
        price > sma200,
        sma20 > sma50,
        sma50 > sma200,   # golden cross condition
    ])
    if bulls >= 4:
        return "BUY",  0.60 + 0.08 * (bulls - 4)
    elif bulls <= 1:
        return "SELL", 0.60 + 0.08 * (2 - bulls)
    return "HOLD", 0.50


def _macd_signal(row: dict) -> tuple[str, float]:
    """MACD line vs signal line crossover."""
    macd   = row.get("MACD",        np.nan)
    signal = row.get("MACD_Signal", np.nan)
    hist   = row.get("MACD_Hist",   np.nan)
    if any(np.isnan(v) for v in [macd, signal, hist]):
        return "HOLD", 0.5
    if macd > signal and hist > 0:
        return "BUY",  min(0.5 + abs(hist) / (abs(macd) + 1e-9) * 0.5, 0.95)
    elif macd < signal and hist < 0:
        return "SELL", min(0.5 + abs(hist) / (abs(macd) + 1e-9) * 0.5, 0.95)
    return "HOLD", 0.50


def _rsi_signal(row: dict) -> tuple[str, float]:
    """Classic RSI oversold/overbought zones."""
    rsi = row.get("RSI", np.nan)
    if np.isnan(rsi):
        return "HOLD", 0.5
    if rsi < 30:
        return "BUY",  0.55 + (30 - rsi) / 30 * 0.35
    elif rsi > 70:
        return "SELL", 0.55 + (rsi - 70) / 30 * 0.35
    return "HOLD", 0.5


def _bollinger_signal(row: dict) -> tuple[str, float]:
    """Bollinger Band %B — mean reversion."""
    bb_pct = row.get("BB_Pct", np.nan)
    if np.isnan(bb_pct):
        return "HOLD", 0.5
    if bb_pct < 0.05:
        return "BUY",  0.60 + (0.05 - bb_pct) * 5
    elif bb_pct > 0.95:
        return "SELL", 0.60 + (bb_pct - 0.95) * 5
    return "HOLD", 0.5


def _stochastic_signal(row: dict) -> tuple[str, float]:
    """Stochastic oversold/overbought."""
    k = row.get("Stoch_K", np.nan)
    d = row.get("Stoch_D", np.nan)
    if any(np.isnan(v) for v in [k, d]):
        return "HOLD", 0.5
    if k < 20 and d < 20 and k > d:
        return "BUY",  0.62
    elif k > 80 and d > 80 and k < d:
        return "SELL", 0.62
    return "HOLD", 0.50


# ── Composite Signal ──────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "trend":       0.30,
    "macd":        0.25,
    "rsi":         0.20,
    "bollinger":   0.15,
    "stochastic":  0.10,
}

def _composite_signal(row: dict) -> dict:
    signals = {
        "trend":      _trend_signal(row),
        "macd":       _macd_signal(row),
        "rsi":        _rsi_signal(row),
        "bollinger":  _bollinger_signal(row),
        "stochastic": _stochastic_signal(row),
    }

    buy_score  = 0.0
    sell_score = 0.0
    hold_score = 0.0

    for name, (sig, conf) in signals.items():
        w = SIGNAL_WEIGHTS[name]
        if sig == "BUY":
            buy_score  += w * conf
        elif sig == "SELL":
            sell_score += w * conf
        else:
            hold_score += w * conf

    total = buy_score + sell_score + hold_score
    if total == 0:
        return {"signal": "HOLD", "confidence": 50, "breakdown": {}}

    # Normalise
    buy_pct  = buy_score  / total
    sell_pct = sell_score / total
    hold_pct = hold_score / total

    if buy_pct >= sell_pct and buy_pct >= hold_pct:
        final, raw_conf = "BUY",  buy_pct
    elif sell_pct >= buy_pct and sell_pct >= hold_pct:
        final, raw_conf = "SELL", sell_pct
    else:
        final, raw_conf = "HOLD", hold_pct

    confidence = round(raw_conf * 100, 1)

    breakdown = {
        name: {"signal": sig, "confidence": round(conf * 100, 1)}
        for name, (sig, conf) in signals.items()
    }

    return {
        "signal":      final,
        "confidence":  confidence,
        "buy_score":   round(buy_pct * 100,  1),
        "sell_score":  round(sell_pct * 100, 1),
        "hold_score":  round(hold_pct * 100, 1),
        "breakdown":   breakdown,
    }


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/predict/{symbol}")
def predict(
    symbol: str,
    period: str = Query("6mo", description="History period for indicator calculation"),
):
    """
    Returns a composite AI trade signal combining five technical sub-signals:
    trend (MA crossovers), MACD, RSI, Bollinger Bands, and Stochastic.
    Each sub-signal has an individual confidence score; the composite is
    a weighted average.
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        hist   = ticker.history(period=period)
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data found for '{symbol}'.")

        df = add_features(hist.reset_index())
        df = df.dropna(subset=["SMA_20", "RSI", "MACD"])
        if df.empty:
            raise HTTPException(
                status_code=422,
                detail="Insufficient data to compute indicators. Try a longer period.",
            )

        row = df.iloc[-1].to_dict()
        composite = _composite_signal(row)

        current_price = round(float(row["Close"]), 4)
        atr           = row.get("ATR", np.nan)
        bb_width      = row.get("BB_Width", np.nan)

        # Simple price targets based on ATR
        stop_loss  = None
        take_profit = None
        if not np.isnan(atr):
            multiplier  = 1.5
            if composite["signal"] == "BUY":
                stop_loss   = round(current_price - multiplier * atr, 4)
                take_profit = round(current_price + 2 * multiplier * atr, 4)
            elif composite["signal"] == "SELL":
                stop_loss   = round(current_price + multiplier * atr, 4)
                take_profit = round(current_price - 2 * multiplier * atr, 4)

        return _sanitize({
            "symbol":        symbol.upper(),
            "current_price": current_price,
            "period":        period,
            # Core signal
            **composite,
            # Indicators snapshot
            "indicators": {
                "rsi":          round(float(row.get("RSI",        np.nan) or 0), 2),
                "macd":         round(float(row.get("MACD",       np.nan) or 0), 4),
                "macd_signal":  round(float(row.get("MACD_Signal",np.nan) or 0), 4),
                "sma_20":       round(float(row.get("SMA_20",     np.nan) or 0), 4),
                "sma_50":       round(float(row.get("SMA_50",     np.nan) or 0), 4),
                "sma_200":      round(float(row.get("SMA_200",    np.nan) or 0), 4),
                "bb_upper":     round(float(row.get("BB_Upper",   np.nan) or 0), 4),
                "bb_lower":     round(float(row.get("BB_Lower",   np.nan) or 0), 4),
                "bb_pct":       round(float(row.get("BB_Pct",     np.nan) or 0), 4),
                "atr":          round(float(atr) if not np.isnan(atr) else 0, 4),
                "stoch_k":      round(float(row.get("Stoch_K",   np.nan) or 0), 2),
                "stoch_d":      round(float(row.get("Stoch_D",   np.nan) or 0), 2),
                "volatility":   round(float(row.get("Volatility_20", np.nan) or 0), 4),
                "return_1d":    round(float(row.get("Return_1d", np.nan) or 0) * 100, 2),
                "return_5d":    round(float(row.get("Return_5d", np.nan) or 0) * 100, 2),
            },
            "risk_management": {
                "stop_loss":   stop_loss,
                "take_profit": take_profit,
                "atr":         round(float(atr) if not np.isnan(atr) else 0, 4),
            },
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Prediction error for %s", symbol)
        raise HTTPException(status_code=500, detail=str(exc))
