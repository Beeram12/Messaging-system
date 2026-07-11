from datetime import timedelta

import pytest
from freezegun import freeze_time

from app.core.config import get_settings
from app.repositories.rate_limit_repository import RateLimitRepository
from app.services.rate_limiter import RateLimitExceededError, RateLimiter


@pytest.fixture()
def rate_limiter(db_session, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "5")
    get_settings.cache_clear()
    yield RateLimiter(RateLimitRepository(db_session))
    monkeypatch.delenv("RATE_LIMIT_PER_HOUR", raising=False)
    get_settings.cache_clear()


def test_first_request_creates_full_bucket_minus_one(rate_limiter, db_session):
    with freeze_time("2026-01-01 00:00:00"):
        rate_limiter.check("user-1")

    bucket = RateLimitRepository(db_session).get_for_update("user-1")
    assert bucket.tokens == 4  # capacity 5, minus 1 consumed


def test_allows_burst_up_to_capacity(rate_limiter):
    with freeze_time("2026-01-01 00:00:00"):
        for _ in range(5):
            rate_limiter.check("user-2")  # capacity is 5, all should succeed


def test_rejects_request_once_bucket_is_empty(rate_limiter):
    with freeze_time("2026-01-01 00:00:00"):
        for _ in range(5):
            rate_limiter.check("user-3")

        with pytest.raises(RateLimitExceededError):
            rate_limiter.check("user-3")


def test_tokens_refill_over_time(rate_limiter):
    with freeze_time("2026-01-01 00:00:00") as frozen_time:
        for _ in range(5):
            rate_limiter.check("user-4")  # bucket now empty

        with pytest.raises(RateLimitExceededError):
            rate_limiter.check("user-4")

        # capacity=5/hour -> refill rate = 5/3600s; waiting 720s refills 1 token
        frozen_time.tick(timedelta(seconds=720))
        rate_limiter.check("user-4")  # should succeed now that >=1 token refilled


def test_refill_never_exceeds_capacity(rate_limiter, db_session):
    with freeze_time("2026-01-01 00:00:00") as frozen_time:
        rate_limiter.check("user-5")  # consumes 1, bucket = capacity - 1

        # wait a very long time - refill should cap at capacity, not overflow
        frozen_time.tick(timedelta(hours=100))
        rate_limiter.check("user-5")

    bucket = RateLimitRepository(db_session).get_for_update("user-5")
    capacity = get_settings().rate_limit_per_hour
    assert bucket.tokens == capacity - 1


def test_different_users_have_independent_buckets(rate_limiter):
    with freeze_time("2026-01-01 00:00:00"):
        for _ in range(5):
            rate_limiter.check("user-a")

        # user-b's bucket is untouched by user-a's usage
        rate_limiter.check("user-b")
