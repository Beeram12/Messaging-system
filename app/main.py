from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import configure_logging, get_logger
from app.routers import notifications, preferences

configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="Notification Service",
    description="Multi-channel (email/SMS/push) notification service with priority delivery, "
    "retries, idempotency, and rate limiting.",
    version="1.0.0",
)

app.include_router(notifications.router)
app.include_router(preferences.router)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning("validation_error", path=str(request.url), error=str(exc))
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
