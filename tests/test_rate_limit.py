"""The token bucket math, tested without a database."""

from backend.app.services.rate_limit import refill, seconds_until_next_token

CAPACITY, PERIOD = 10, 1800  # 10 tokens per 30 minutes = 1 token every 180 s


def test_one_token_comes_back_every_three_minutes() -> None:
    assert refill(0, 180, CAPACITY, PERIOD) == 1


def test_bucket_never_exceeds_capacity() -> None:
    assert refill(9.5, 10_000, CAPACITY, PERIOD) == CAPACITY


def test_clock_going_backwards_adds_nothing() -> None:
    assert refill(4, -60, CAPACITY, PERIOD) == 4


def test_wait_time_for_next_token() -> None:
    assert seconds_until_next_token(0, CAPACITY, PERIOD) == 180
    assert seconds_until_next_token(0.5, CAPACITY, PERIOD) == 90
