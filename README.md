# InttelTrade AI — v2.0 (Advanced)

AI-powered stock analysis platform with real-time market data, multi-signal trade signals,
JWT authentication, and an interactive trading dashboard.

---

## What Was Fixed & Improved

### Security
| Before | After |
|---|---|
| Passwords printed to console in plain text | Debug logs removed |
| `pbkdf2_sha256` (weaker) | `bcrypt` (industry standard) |
| No JWT — login returned raw username | Full JWT access + refresh token flow |
| No token expiry or validation | Tokens expire; protected routes verify `Bearer` |
| Passwords not validated for strength | Pydantic validator enforces 8+ chars, uppercase, digit |
| Username not validated | Regex validation, length limits |

### Architecture
| Before | After |
|---|---|
| `Base.metadata.create_all` called at import time in auth.py | Proper `lifespan` startup hook in `main.py` |
| `declarative_base` from deprecated path | Updated to `sqlalchemy.orm.declarative_base` |
| No global error handling | `@app.exception_handler(Exception)` catches all unhandled errors |
| No rate limiting | `slowapi` rate limiter on all routes |
| Hard-coded database URL | `pydantic-settings` + `.env` file |
| No `get_db` in `database.py` (duplicated in auth.py) | Canonical `get_db()` dependency in `database.py` |

### AI / Prediction Engine
| Before | After |
|---|---|
| Simple 10/30 MA crossover (3 possible signals) | 5 sub-signals: Trend, MACD, RSI, Bollinger Bands, Stochastic |
| Hard-coded confidence (85/80/65) | Weighted composite confidence score (dynamic, per-signal) |
| No explanation of signal | Full breakdown per sub-signal with individual confidence |
| No risk management | ATR-based stop loss and take profit levels |
| RSI with simple rolling mean (incorrect Wilder formula) | Correct Wilder RSI using EWM |

### API
| Before | After |
|---|---|
| `/stock/{symbol}` returned only symbol + price | Returns 15+ fields: change, %, volume, market cap, 52W range, P/E |
| No history endpoint | `GET /stock/{symbol}/history?period=3mo` returns full OHLCV |
| No company info endpoint | `GET /stock/{symbol}/info` returns fundamentals |
| `predict` endpoint had trailing space in "BUY " | Fixed |

### Frontend
| Before | After |
|---|---|
| No frontend included | Full trading dashboard (`frontend/dashboard.html`) |
| — | Live price chart with SMA overlays (Chart.js) |
| — | Signal breakdown visualization (5 sub-signals) |
| — | RSI / Bollinger / Stochastic indicator gauges |
| — | Persistent watchlist with live prices |
| — | JWT-based login / register with bcrypt |
| — | ATR stop-loss / take-profit display |

---

## Quick Start

```bash
cd backend

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — especially SECRET_KEY for production

# 3. Run the server
uvicorn main:app --reload --port 

# 4. Open the dashboard
# Open frontend/dashboard.html in your browser (or serve with Live Server)
```

Interactive API docs: http://localhost:8000/docs

---

## Project Structure

```
InttelTrade_Advanced/
├── backend/
│   ├── main.py                      # FastAPI app + lifespan
│   ├── config.py                    # Pydantic Settings (env vars)
│   ├── database.py                  # SQLAlchemy engine + get_db()
│   ├── models.py                    # User, WatchlistItem ORM models
│   ├── requirements.txt
│   ├── .env.example
│   ├── api/
│   │   ├── auth.py                  # Register / Login / Refresh / Me
│   │   ├── stock.py                 # Quote / History / Fundamentals
│   │   └── predict.py               # 5-signal composite AI prediction
│   ├── middleware/
│   │   ├── jwt_utils.py             # create/decode access+refresh tokens
│   │   └── dependencies.py          # get_current_user FastAPI dependency
│   └── utils/
│       └── feature_engineering.py   # 15+ technical indicators
└── frontend/
    └── dashboard.html               # Full trading UI (zero dependencies)
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | No | Create account |
| POST | `/api/v1/auth/login` | No | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | No | Renew access token |
| GET | `/api/v1/auth/me` | Yes | Current user profile |
| GET | `/api/v1/stock/{symbol}` | No | Live quote |
| GET | `/api/v1/stock/{symbol}/history` | No | OHLCV history |
| GET | `/api/v1/stock/{symbol}/info` | No | Company fundamentals |
| GET | `/api/v1/predict/{symbol}` | No | AI trade signal |

---

## Disclaimer

This platform is for educational purposes only. It is not financial advice.
Always do your own research before making investment decisions.
