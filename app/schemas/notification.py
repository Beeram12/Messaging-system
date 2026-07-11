import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Channel, NotificationStatus, Priority


class NotificationCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    channel: Channel
    priority: Priority = Priority.NORMAL

    template_id: Optional[str] = Field(default=None, description="ID of a stored template to render")
    variables: dict = Field(default_factory=dict, description="Variables for template substitution")

    subject: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None, description="Raw message body, used if template_id is not set")

    idempotency_key: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_body_or_template(self) -> "NotificationCreateRequest":
        if not self.template_id and not self.body:
            raise ValueError("Either 'template_id' or 'body' must be provided")
        return self


class NotificationAttemptResponse(BaseModel):
    attempt_number: int
    status: NotificationStatus
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    channel: Channel
    priority: Priority
    status: NotificationStatus
    subject: Optional[str] = None
    body: str
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationDetailResponse(NotificationResponse):
    attempts: list[NotificationAttemptResponse] = Field(default_factory=list)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int
