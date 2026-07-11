import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.dependencies import require_api_key
from app.schemas.notification import (
    NotificationCreateRequest,
    NotificationDetailResponse,
    NotificationListResponse,
    NotificationResponse,
)
from app.services.notification_service import NotificationService, TemplateNotFoundError
from app.services.rate_limiter import RateLimitExceededError
from app.services.template_engine import TemplateRenderError

router = APIRouter(tags=["notifications"], dependencies=[Depends(require_api_key)])
logger = get_logger(__name__)


@router.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_notification(request: NotificationCreateRequest, db: Session = Depends(get_db)):
    service = NotificationService(db)
    try:
        notification, created = service.create_notification(request)
        db.commit()
    except TemplateNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TemplateRenderError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    db.refresh(notification)
    return NotificationResponse.model_validate(notification)


@router.get("/notifications/{notification_id}", response_model=NotificationDetailResponse)
def get_notification(notification_id: uuid.UUID, db: Session = Depends(get_db)):
    service = NotificationService(db)
    notification = service.get_notification(notification_id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationDetailResponse.model_validate(notification)


@router.get("/users/{user_id}/notifications", response_model=NotificationListResponse)
def list_user_notifications(
    user_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    service = NotificationService(db)
    items, total = service.list_user_notifications(user_id, limit, offset)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
