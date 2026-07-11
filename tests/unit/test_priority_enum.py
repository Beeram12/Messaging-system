from app.models.enums import Priority


def test_priority_queue_weight_ordering():
    weights = {p: p.queue_weight for p in Priority}
    assert weights[Priority.CRITICAL] < weights[Priority.HIGH]
    assert weights[Priority.HIGH] < weights[Priority.NORMAL]
    assert weights[Priority.NORMAL] < weights[Priority.LOW]
