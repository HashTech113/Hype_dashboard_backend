from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class DateRange(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check(self) -> "DateRange":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class EmployeeReportRequest(DateRange):
    employee_id: int = Field(gt=0)


class MonthlyReportRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
