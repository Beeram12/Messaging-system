from app.core.config import get_settings


def compute_backoff_delay_ms(retry_count: int) -> int:
    """Exponential backoff: base * 2^retry_count, in milliseconds.

    retry_count is the number of attempts already made (0 for the first retry).
    """
    settings = get_settings()
    delay_seconds = settings.retry_base_delay_seconds * (2**retry_count)
    return delay_seconds * 1000


def has_retries_remaining(retry_count: int) -> bool:
    return retry_count < get_settings().max_retries
