from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.admins import router as admins_router
from app.api.v1.attendance import router as attendance_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cameras import router as cameras_router
from app.api.v1.employees import router as employees_router
from app.api.v1.recognition import router as recognition_router
from app.api.v1.reports import router as reports_router
from app.api.v1.settings import router as settings_router
from app.api.v1.snapshots import router as snapshots_router
from app.api.v1.training import router as training_router
from app.api.v1.unknowns import router as unknowns_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(employees_router)
api_router.include_router(training_router)
api_router.include_router(cameras_router)
api_router.include_router(attendance_router)
api_router.include_router(recognition_router)
api_router.include_router(snapshots_router)
api_router.include_router(reports_router)
api_router.include_router(settings_router)
api_router.include_router(unknowns_router)
api_router.include_router(admin_router)
api_router.include_router(admins_router)
api_router.include_router(compliance_router)
