"""
Main FastAPI application entry point.

Single application on port 9187 (HTTP), served behind Nginx Proxy Manager (TLS/HTTPS).
Loads configuration from ROOT .env file.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, validate_config
from app.core.middleware import RequestContextMiddleware
from app.routers import (
    admin,
    auth,
    metric_categories,
    metric_synonyms,
    metrics,
    participants,
    prof_activities,
    reports,
    scoring,
    weights,
)

logger = logging.getLogger("app.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("application_starting", extra={"event": "startup"})

    # Validate configuration
    validate_config()

    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    # TODO: Initialize Celery client

    # Auto-seed MetricDef if table is empty (works in all environments)
    # This ensures metrics are available even in production if database is fresh
    try:
        from app.core.config import settings as app_settings
        from app.db.session import AsyncSessionLocal
        from app.repositories.metric import MetricDefRepository
        from app.services.metric_mapping import MetricMappingService
        from app.services.metric_localization import get_metric_display_name_ru

        async with AsyncSessionLocal() as db_session:  # type: AsyncSession
            metric_repo = MetricDefRepository(db_session)
            existing_metrics = await metric_repo.list_all(active_only=False)
            if not existing_metrics:
                logger.info("metric_defs_seeding_started", extra={"event": "seed_start", "env": app_settings.env})
                mapping_service = MetricMappingService()
                mapping_service.load()
                # Unified mapping: get all metric codes from the single header_map
                all_codes: set[str] = set(mapping_service.get_all_mappings().values())
                created = 0
                for code in sorted(all_codes):
                    name = code.replace("_", " ").title()
                    name_ru = get_metric_display_name_ru(code)
                    await metric_repo.create(
                        code=code,
                        name=name,
                        name_ru=name_ru or name,
                        description=None,
                        unit="балл",
                        min_value=Decimal("1"),
                        max_value=Decimal("10"),
                        active=True,
                    )
                    created += 1
                logger.info(
                    "metric_defs_seeded",
                    extra={"event": "seed_complete", "created_count": created, "env": app_settings.env},
                )
            else:
                missing_localized = 0
                for metric in existing_metrics:
                    if not metric.name_ru or not metric.name_ru.strip():
                        name_ru = get_metric_display_name_ru(metric.code)
                        if name_ru:
                            metric.name_ru = name_ru
                            missing_localized += 1

                if missing_localized:
                    await db_session.commit()
                    logger.info(
                        "metric_defs_localized",
                        extra={
                            "event": "seed_localize",
                            "updated_count": missing_localized,
                            "env": app_settings.env,
                        },
                    )
                else:
                    logger.debug(
                        "metric_defs_already_exist",
                        extra={
                            "event": "seed_skip",
                            "count": len(existing_metrics),
                            "env": app_settings.env,
                        },
                    )
    except Exception as exc:  # noqa: BLE001
        # Do not fail startup; log and continue
        logger.exception("metric_defs_seeding_failed", extra={"error": str(exc)})

    logger.info("application_ready", extra={"event": "ready", "port": settings.app_port})

    yield

    # Shutdown
    logger.info("application_shutting_down", extra={"event": "shutdown"})

    # TODO: Close database connections
    # TODO: Close Redis connections
    # TODO: Close Celery connections

    logger.info("application_shutdown_complete", extra={"event": "shutdown_complete"})


# Create FastAPI Application
app = FastAPI(
    title="Workers Proficiency Assessment API",
    description=(
        "Professional competency assessment system. "
        "Extracts metrics from reports, calculates fitness scores, "
        "and generates personalized recommendations."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    root_path=settings.app_root_path,
    lifespan=lifespan,
)


# Observability Middleware
app.add_middleware(RequestContextMiddleware)

# CORS Middleware
if settings.cors_allow_all or settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Global Error Handlers
@app.exception_handler(SQLAlchemyError)
async def handle_sqlalchemy_error(request: Request, exc: SQLAlchemyError):
    """
    Return 503 instead of 500 when database is unavailable or schema missing.
    Helps frontend surface actionable message instead of generic server error.
    """
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database unavailable or schema not initialized. Please run migrations (alembic upgrade head) and verify POSTGRES_DSN points to a reachable database.",
        },
    )


# Health Check Endpoint
@app.get("/api/healthz", tags=["Health"])
async def healthz():
    """
    Health check endpoint.

    Returns 200 OK if the application is running.
    Used by NPM and monitoring systems.
    """
    return {
        "status": "ok",
        "service": "api-gateway",
        "version": "0.1.0",
        "env": settings.env,
    }


# Register Routers
# IMPORTANT: Register API routers BEFORE StaticFiles mount
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(participants.router, prefix="/api")
app.include_router(prof_activities.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(weights.router, prefix="/api/admin", tags=["Weights"])
app.include_router(metric_categories.router, prefix="/api", tags=["Metric Categories"])
app.include_router(metrics.router)
app.include_router(metric_synonyms.router)
app.include_router(scoring.router, prefix="/api", tags=["Scoring"])


# Static Files & SPA Fallback
# Mount static files (CSS, JS, images, etc.) from /static directory
static_dir = Path(__file__).parent / "static"
assets_dir = static_dir / "assets"

# Mount StaticFiles for serving static assets (JS, CSS, images, etc.)
# IMPORTANT: Mount before catch-all SPA fallback
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static")


@app.get("/{full_path:path}")
async def spa_fallback(request: Request, full_path: str):
    """
    SPA fallback handler for all non-API routes.

    Returns index.html for any path that doesn't start with /api,
    allowing Vue Router (or other SPA frameworks) to handle client-side routing.

    Examples:
        - GET / -> index.html
        - GET /participants -> index.html
        - GET /reports/123 -> index.html
        - GET /api/healthz -> handled by API router (not this handler)
    """
    # If path starts with /api, it should have been handled by API routers
    # If we're here, it means 404 for API endpoint - let FastAPI handle it
    if full_path.startswith("api/"):
        # This will be caught by FastAPI's default 404 handler
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="API endpoint not found")

    # For all other paths, serve index.html for SPA routing
    index_file = static_dir / "index.html"
    return FileResponse(index_file)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.is_dev,
        proxy_headers=settings.uvicorn_proxy_headers,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_level=settings.log_level.lower(),
    )
