from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.symbols import router as symbol_router
from app.api.strategies import router as strategy_router
from app.api.backtests import router as backtest_router
from app.api.runs import router as run_router
from app.api.signal_engine import router as signal_engine_router
from app.api.notifications import router as notification_router
from app.api.logs import router as logs_router

app = FastAPI(title="多资产模拟平台 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symbol_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(run_router)
app.include_router(signal_engine_router)
app.include_router(notification_router)
app.include_router(logs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
