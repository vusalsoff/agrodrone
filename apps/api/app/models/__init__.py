"""Import all ORM models so SQLAlchemy metadata discovers every table."""

from app.models.alert import Alert, AlertRule, Notification, NotificationPreference
from app.models.audit_log import AuditLog
from app.models.detection import DetectionItem, DetectionJob, RegisteredDataset
from app.models.device import Device
from app.models.edge_gateway import EdgeGateway, GatewayConnectivityEvent, StreamSession
from app.models.field import Field
from app.models.media import MediaAsset
from app.models.mission import Mission
from app.models.refresh_token import RefreshToken
from app.models.user import User

__all__ = [
    "Alert",
    "AlertRule",
    "AuditLog",
    "DetectionItem",
    "DetectionJob",
    "Device",
    "EdgeGateway",
    "Field",
    "GatewayConnectivityEvent",
    "MediaAsset",
    "Mission",
    "Notification",
    "NotificationPreference",
    "RefreshToken",
    "RegisteredDataset",
    "StreamSession",
    "User",
]
