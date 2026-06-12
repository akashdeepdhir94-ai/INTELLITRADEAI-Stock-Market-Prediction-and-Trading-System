"""
Market Data API
───────────────
GET /api/v1/stock/{symbol}          — quote + metadata
GET /api/v1/stock/{symbol}/history  — OHLCV history (configurable period)
GET /api/v1/stock/{symbol}/info     — company fundamentals
"""

import math
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
import yfinance as yf

logger = logging.getLogger("intellitrade.stock")
router = APIRouter()

VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}


def _fetch_ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol.upper())


def _sanitize(value: Any) -> Any:
    """Recursively replace NaN/inf with None so JSON serialization never fails."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


# ── Quote ─────────────────────────────────────────────────────────────────────

@router.get("/stock/{symbol}")
def get_quote(symbol: str):
    """Current price, day range, volume, and 52-week range."""
    try:
        ticker = _fetch_ticker(symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data found for symbol '{symbol}'.")

        info = ticker.info or {}
        latest = hist.iloc[-1]
        prev   = hist.iloc[-2] if len(hist) >= 2 else None

        current_price = round(float(latest["Close"]), 4)
        prev_close    = round(float(prev["Close"]), 4) if prev is not None else current_price
        change        = round(current_price - prev_close, 4)
        change_pct    = round((change / prev_close) * 100, 2) if prev_close else 0.0

        return _sanitize({
            "symbol":        symbol.upper(),
            "name":          info.get("shortName", symbol.upper()),
            "currency":      info.get("currency", "USD"),
            "exchange":      info.get("exchange", ""),
            "current_price": current_price,
            "previous_close": prev_close,
            "change":        change,
            "change_pct":    change_pct,
            "open":          round(float(latest.get("Open", 0)), 4),
            "high":          round(float(latest.get("High", 0)), 4),
            "low":           round(float(latest.get("Low",  0)), 4),
            "volume":        int(latest.get("Volume", 0)),
            "market_cap":    info.get("marketCap"),
            "pe_ratio":      info.get("trailingPE"),
            "week_52_high":  info.get("fiftyTwoWeekHigh"),
            "week_52_low":   info.get("fiftyTwoWeekLow"),
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching quote for %s", symbol)
        raise HTTPException(status_code=500, detail=str(exc))


# ── OHLCV History ─────────────────────────────────────────────────────────────

@router.get("/stock/{symbol}/history")
def get_history(
    symbol: str,
    period: str = Query("3mo", description="yfinance period string, e.g. 1mo, 6mo, 1y"),
):
    """OHLCV candlestick data for charting."""
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Choose from: {', '.join(sorted(VALID_PERIODS))}.",
        )
    try:
        ticker = _fetch_ticker(symbol)
        hist   = ticker.history(period=period)
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No history data for '{symbol}'.")

        records = _sanitize([
            {
                "date":   str(idx.date()),
                "open":   round(float(row["Open"]),   4),
                "high":   round(float(row["High"]),   4),
                "low":    round(float(row["Low"]),    4),
                "close":  round(float(row["Close"]),  4),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ])
        return {"symbol": symbol.upper(), "period": period, "data": records}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching history for %s", symbol)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Fundamentals ──────────────────────────────────────────────────────────────

@router.get("/stock/{symbol}/info")
def get_info(symbol: str):
    """Company profile and key financial metrics."""
    try:
        ticker = _fetch_ticker(symbol)
        info   = ticker.info or {}
        if not info:
            raise HTTPException(status_code=404, detail=f"No info found for '{symbol}'.")

        keys = [
            "shortName", "longName", "sector", "industry", "country",
            "website", "longBusinessSummary", "fullTimeEmployees",
            "marketCap", "trailingPE", "forwardPE", "priceToBook",
            "dividendYield", "beta", "earningsGrowth", "revenueGrowth",
            "grossMargins", "operatingMargins", "profitMargins",
            "returnOnEquity", "debtToEquity", "currentRatio",
            "recommendationKey", "targetMeanPrice",
        ]
        return _sanitize({"symbol": symbol.upper(), **{k: info.get(k) for k in keys}})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching info for %s", symbol)
        raise HTTPException(status_code=500, detail=str(exc))
