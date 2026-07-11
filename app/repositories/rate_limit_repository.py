from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rate_limit_bucket import RateLimitBucket


class RateLimitRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_update(self, user_id: str) -> RateLimitBucket | None:
        """Locks the bucket row (if it exists) for the duration of the current
        transaction, so two concurrent requests for the same user can't both
        read the same token count and each think they're allowed to proceed."""
        stmt = select(RateLimitBucket).where(RateLimitBucket.user_id == user_id).with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, user_id: str, tokens: float, last_refill_at: datetime) -> RateLimitBucket:
        bucket = RateLimitBucket(user_id=user_id, tokens=tokens, last_refill_at=last_refill_at)
        self.db.add(bucket)
        self.db.flush()
        return bucket

    def save(self, bucket: RateLimitBucket, tokens: float, last_refill_at: datetime) -> RateLimitBucket:
        bucket.tokens = tokens
        bucket.last_refill_at = last_refill_at
        self.db.flush()
        return bucket
