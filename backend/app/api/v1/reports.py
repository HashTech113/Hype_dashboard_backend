from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.models.admin import Admin
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily.xlsx")
def daily_report(
    work_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Response:
    data = ReportService(db).daily_report(work_date)
    return _xlsx(data, f"attendance_daily_{work_date.isoformat()}.xlsx")


@router.get("/monthly.xlsx")
def monthly_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Response:
    data = ReportService(db).monthly_report(year, month)
    return _xlsx(data, f"attendance_monthly_{year}-{month:02d}.xlsx")


@router.get("/employee/{employee_id}.xlsx")
def employee_report(
    employee_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Response:
    data = ReportService(db).employee_report(employee_id, start_date, end_date)
    return _xlsx(
        data,
        f"attendance_employee_{employee_id}_{start_date}_{end_date}.xlsx",
    )


@router.get("/date-range.xlsx")
def date_range_report(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Response:
    data = ReportService(db).date_range_report(start_date, end_date)
    return _xlsx(data, f"attendance_range_{start_date}_{end_date}.xlsx")
