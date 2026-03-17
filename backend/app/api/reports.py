from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import get_report_service
from app.core.models import PerformanceReport
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/daily", response_model=PerformanceReport)
def get_daily_report(service: ReportService = Depends(get_report_service)) -> PerformanceReport:
    return service.daily()


@router.get("/weekly", response_model=PerformanceReport)
def get_weekly_report(service: ReportService = Depends(get_report_service)) -> PerformanceReport:
    return service.weekly()


@router.get("/range", response_model=PerformanceReport)
def get_range_report(
    start: str = Query(..., description="ISO8601 UTC"),
    end: str = Query(..., description="ISO8601 UTC"),
    service: ReportService = Depends(get_report_service),
) -> PerformanceReport:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(timezone.utc)
    return service.generate(start=start_dt, end=end_dt)


@router.get("/export.csv")
def export_report_csv(
    start: str = Query(..., description="ISO8601 UTC"),
    end: str = Query(..., description="ISO8601 UTC"),
    service: ReportService = Depends(get_report_service),
) -> Response:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(timezone.utc)
    report = service.generate(start=start_dt, end=end_dt)
    content = service.export_csv(report)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="performance_report.csv"'},
    )
