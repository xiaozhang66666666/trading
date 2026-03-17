from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.models import Kline, KlineQualityReport, MarketOverview, MarketType, SessionIntegrity, Symbol
from app.services.data_source_registry import DataSourceRegistry
from app.services.market_session import MarketSessionService


@dataclass
class _QualityStats:
    total_points: int
    duplicate_points: int
    out_of_order_points: int
    missing_points: int
    invalid_price_points: int


class MarketDataService:
    def __init__(self, registry: DataSourceRegistry, session_service: MarketSessionService) -> None:
        self._registry = registry
        self._session_service = session_service

    @staticmethod
    def _interval_seconds(interval: str) -> int:
        mapping = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return mapping.get(interval, 900)

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _normalize_klines(self, candles: list[Kline]) -> tuple[list[Kline], _QualityStats]:
        if not candles:
            return (
                [],
                _QualityStats(total_points=0, duplicate_points=0, out_of_order_points=0, missing_points=0, invalid_price_points=0),
            )

        duplicate_points = 0
        out_of_order_points = 0
        invalid_price_points = 0
        missing_points = 0

        last_dt: datetime | None = None
        for candle in candles:
            current = self._parse_iso(candle.open_time)
            if last_dt and current < last_dt:
                out_of_order_points += 1
            last_dt = current
            if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
                invalid_price_points += 1
            if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
                invalid_price_points += 1

        ordered = sorted(candles, key=lambda c: c.open_time)
        deduped: list[Kline] = []
        seen: set[str] = set()
        for candle in ordered:
            if candle.open_time in seen:
                duplicate_points += 1
                continue
            seen.add(candle.open_time)
            deduped.append(candle)

        return (
            deduped,
            _QualityStats(
                total_points=len(deduped),
                duplicate_points=duplicate_points,
                out_of_order_points=out_of_order_points,
                missing_points=missing_points,
                invalid_price_points=invalid_price_points,
            ),
        )

    def _fill_missing_klines(self, candles: list[Kline], interval: str) -> tuple[list[Kline], int, int]:
        if len(candles) < 2:
            return candles, 0, 0

        interval_seconds = self._interval_seconds(interval)
        expected_delta = timedelta(seconds=interval_seconds)
        completed: list[Kline] = [candles[0]]
        filled = 0
        missing = 0

        for idx in range(1, len(candles)):
            prev = completed[-1]
            curr = candles[idx]
            prev_open = self._parse_iso(prev.open_time)
            curr_open = self._parse_iso(curr.open_time)
            gap_seconds = int((curr_open - prev_open).total_seconds())
            if gap_seconds > interval_seconds:
                gap_missing = max(gap_seconds // interval_seconds - 1, 0)
                missing += gap_missing
                for gap_idx in range(gap_missing):
                    open_time = prev_open + expected_delta * (gap_idx + 1)
                    close_time = open_time + expected_delta
                    synthetic = Kline(
                        open_time=open_time.isoformat(),
                        close_time=close_time.isoformat(),
                        open=prev.close,
                        high=prev.close,
                        low=prev.close,
                        close=prev.close,
                        volume=0.0,
                    )
                    completed.append(synthetic)
                    prev = synthetic
                    filled += 1
            completed.append(curr)

        return completed, missing, filled

    def _session_integrity(self, market: MarketType, candles: list[Kline], interval: str) -> SessionIntegrity:
        if market != MarketType.US_EQUITY or not candles:
            return SessionIntegrity()

        ny_tz = ZoneInfo("America/New_York")
        interval_seconds = self._interval_seconds(interval)
        minutes = max(interval_seconds // 60, 1)
        latest_dt = self._parse_iso(candles[-1].open_time).astimezone(ny_tz)
        trading_day = latest_dt.date()

        pre_count = 0
        regular_count = 0
        after_count = 0
        for candle in candles:
            local = self._parse_iso(candle.open_time).astimezone(ny_tz)
            if local.date() != trading_day:
                continue
            minute = local.hour * 60 + local.minute
            if 240 <= minute < 570:
                pre_count += 1
            elif 570 <= minute < 960:
                regular_count += 1
            elif 960 <= minute < 1200:
                after_count += 1

        expected_pre = max(330 // minutes, 1)
        expected_regular = max(390 // minutes, 1)
        expected_after = max(240 // minutes, 1)

        pre_ratio = min(pre_count / expected_pre, 1.0)
        regular_ratio = min(regular_count / expected_regular, 1.0)
        after_ratio = min(after_count / expected_after, 1.0)

        issues: list[str] = []
        if regular_ratio < 0.7:
            issues.append("常规时段K线覆盖率偏低")
        if pre_ratio < 0.3:
            issues.append("盘前K线覆盖不足")
        if after_ratio < 0.3:
            issues.append("盘后K线覆盖不足")

        return SessionIntegrity(
            pre_market_ratio=round(pre_ratio, 4),
            regular_ratio=round(regular_ratio, 4),
            after_hours_ratio=round(after_ratio, 4),
            checked_trading_day=trading_day.isoformat(),
            issues=issues,
        )

    def _build_quality(
        self,
        symbol: Symbol,
        interval: str,
        stats: _QualityStats,
        session_integrity: SessionIntegrity,
    ) -> KlineQualityReport:
        issue_count = (
            stats.duplicate_points
            + stats.out_of_order_points
            + stats.invalid_price_points
            + stats.missing_points
            + len(session_integrity.issues)
        )
        score = max(0.0, min(100.0, 100.0 - issue_count * 3.5))
        if score >= 90:
            level = "GOOD"
        elif score >= 75:
            level = "WARN"
        else:
            level = "BAD"

        issues: list[str] = []
        if stats.duplicate_points:
            issues.append(f"检测到重复K线 {stats.duplicate_points} 条")
        if stats.out_of_order_points:
            issues.append(f"检测到乱序K线 {stats.out_of_order_points} 条")
        if stats.missing_points:
            issues.append(f"检测到缺失K线 {stats.missing_points} 条")
        if stats.invalid_price_points:
            issues.append(f"检测到异常价格K线 {stats.invalid_price_points} 条")
        issues.extend(session_integrity.issues)

        return KlineQualityReport(
            symbol=symbol.code,
            interval=interval,
            total_points=stats.total_points,
            duplicate_points=stats.duplicate_points,
            out_of_order_points=stats.out_of_order_points,
            missing_points=stats.missing_points,
            filled_points=0,
            invalid_price_points=stats.invalid_price_points,
            session_integrity=session_integrity,
            score=round(score, 2),
            level=level,
            issues=issues,
        )

    async def get_kline_quality(self, symbol: Symbol, interval: str, limit: int) -> KlineQualityReport:
        source = self._registry.get(symbol.datasource)
        raw = await source.fetch_klines(symbol.code, interval, limit)
        normalized, stats = self._normalize_klines(raw)
        _, missing_points, filled_points = self._fill_missing_klines(normalized, interval)
        session_integrity = self._session_integrity(symbol.market, normalized, interval)
        quality = self._build_quality(symbol=symbol, interval=interval, stats=stats, session_integrity=session_integrity)
        return quality.model_copy(update={"missing_points": missing_points, "filled_points": filled_points})

    async def get_overview(self, symbol: Symbol) -> MarketOverview:
        source = self._registry.get(symbol.datasource)
        session = self._session_service.get_session(symbol.market)
        quote = await source.fetch_quote(symbol.code)
        quality = await self.get_kline_quality(symbol=symbol, interval="1m", limit=120)
        if quality.level != "GOOD":
            quote = quote.model_copy(update={"detail": f"{quote.detail} | 质量{quality.level}: {'; '.join(quality.issues[:2])}"})
        return MarketOverview(
            symbol=symbol.code,
            market=symbol.market,
            session=session.session,
            session_label=session.label,
            quote=quote,
        )

    async def get_klines(self, symbol: Symbol, interval: str, limit: int) -> list[Kline]:
        source = self._registry.get(symbol.datasource)
        raw = await source.fetch_klines(symbol.code, interval, limit)
        normalized, _ = self._normalize_klines(raw)
        completed, _, _ = self._fill_missing_klines(normalized, interval)
        return completed
