from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.symbols import router as symbol_router

app = FastAPI(title="多资产模拟平台 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symbol_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
