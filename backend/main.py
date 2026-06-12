"""
InttelTrade AI — Backend Entry Point
Advanced FastAPI application with JWT auth, rate limiting, and structured logging.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import engine, Base
from api.auth import router as auth_router
from api.stock import router as stock_router
from api.predict import router as predict_router

# ── Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("intellitrade")

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables…")
    Base.metadata.create_all(bind=engine)
    logger.info("InttelTrade AI backend started ✓")
    yield
    logger.info("InttelTrade AI backend shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="IntelTrade AI Stock market and trading system",
    description="AI-powered stock analysis and trade signal platform.",
    version="2.0.0",
    lifespan=lifespan,
)

# Rate-limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router,    prefix="/api/v1/auth",    tags=["Authentication"])
app.include_router(stock_router,   prefix="/api/v1",         tags=["Market Data"])
app.include_router(predict_router, prefix="/api/v1",         tags=["AI Predictions"])


# ── Health / Root ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "InttelTrade AI", "version": "2.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )
