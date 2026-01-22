"""
API routers.
"""

from app.routers import (
    admin,
    auth,
    metric_synonyms,
    participants,
    prof_activities,
    reports,
    weights,
)

__all__ = [
    "auth",
    "admin",
    "metric_synonyms",
    "participants",
    "prof_activities",
    "reports",
    "weights",
]
