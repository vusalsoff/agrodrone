"""Aggregate API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    alerts,
    analytics,
    auth,
    detections,
    devices,
    fields,
    gateway,
    health,
    media,
    missions,
    reports,
    system,
)

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(system.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(fields.router)
api_v1_router.include_router(devices.router)
api_v1_router.include_router(missions.router)
api_v1_router.include_router(media.router)
api_v1_router.include_router(detections.router)
api_v1_router.include_router(gateway.router)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(alerts.router)
api_v1_router.include_router(reports.router)
