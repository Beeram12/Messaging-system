from app.services.retry_policy import compute_backoff_delay_ms, has_retries_remaining


def test_backoff_delay_grows_exponentially():
    delays = [compute_backoff_delay_ms(i) for i in range(3)]
    assert delays == [5000, 10000, 20000]


def test_has_retries_remaining_true_below_max():
    assert has_retries_remaining(0) is True
    assert has_retries_remaining(2) is True


def test_has_retries_remaining_false_at_max():
    assert has_retries_remaining(3) is False
    assert has_retries_remaining(4) is False
