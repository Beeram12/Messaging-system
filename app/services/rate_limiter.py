from datetime import datetime, timezone

from app.core.config import get_settings
from app.repositories.rate_limit_repository import RateLimitRepository


class RateLimitExceededError(Exception):
    def __init__(self, user_id: str, limit: int):
        self.user_id = user_id
        self.limit = limit
        super().__init__(f"User '{user_id}' exceeded rate limit of {limit}/hour")


class RateLimiter:
    """Token-bucket rate limiter (per user, per hour).

    Each user has a bucket that holds up to `rate_limit_per_hour` tokens
    (the burst capacity). The bucket continuously refills at a rate of
    `rate_limit_per_hour` tokens per hour. Sending one notification costs
    one token. If the bucket is empty, the request is rejected.

    Concretely: with a limit of 100/hour, a user starts with 100 tokens and
    can burst through all 100 immediately if they want. After that, tokens
    trickle back in at 100/3600 ≈ 0.0278 tokens/second, so a full recharge
    to sending 1 notification takes 36 seconds, not "wait until the top of
    the next clock hour" like a fixed-window limiter would require.
    """

    def __init__(self, rate_limit_repo: RateLimitRepository):
        self.rate_limit_repo = rate_limit_repo
        self.settings = get_settings()

    def check(self, user_id: str) -> None:
        capacity = float(self.settings.rate_limit_per_hour)
        refill_rate_per_second = capacity / 3600.0
        now = datetime.now(timezone.utc)

        bucket = self.rate_limit_repo.get_for_update(user_id)

        if bucket is None:
            # First request ever for this user: start with a full bucket,
            # minus the one token this request is about to consume.
            self.rate_limit_repo.create(user_id, tokens=capacity - 1, last_refill_at=now)
            return

        elapsed_seconds = max(0.0, (now - bucket.last_refill_at).total_seconds())
        refilled_tokens = min(capacity, bucket.tokens + elapsed_seconds * refill_rate_per_second)

        if refilled_tokens < 1:
            self.rate_limit_repo.save(bucket, tokens=refilled_tokens, last_refill_at=now)
            raise RateLimitExceededError(user_id, self.settings.rate_limit_per_hour)

        self.rate_limit_repo.save(bucket, tokens=refilled_tokens - 1, last_refill_at=now)
