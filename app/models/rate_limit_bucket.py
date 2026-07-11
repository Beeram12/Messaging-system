from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RateLimitBucket(Base):
    """Token-bucket state for per-user rate limiting: one row per user."""

    __tablename__ = "rate_limit_buckets"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    last_refill_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
