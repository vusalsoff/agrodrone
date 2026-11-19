"""Phase 5 Smart Analytics & Map Analytics FastAPI endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DBSessionDep
from app.schemas.analytics import AnalyticsOverviewResponse, MapAnalyticsResponse
from app.services.analytics import get_analytics_overview, get_map_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Get real database-backed analytics summary",
)
def read_analytics_overview(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD or datetime"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD or datetime"),
    field_id: uuid.UUID | None = Query(default=None),
    mission_id: uuid.UUID | None = Query(default=None),
) -> AnalyticsOverviewResponse:
    return get_analytics_overview(
        db,
        current_user,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
    )


@router.get(
    "/map-summary",
    response_model=MapAnalyticsResponse,
    summary="Get field-level map analytics and verified geotagged media points",
)
def read_map_analytics(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> MapAnalyticsResponse:
    return get_map_analytics(
        db,
        current_user,
        date_from=date_from,
        date_to=date_to,
    )
