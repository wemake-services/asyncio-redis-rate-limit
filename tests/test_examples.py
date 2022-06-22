import asyncio
import datetime as dt
import os
from typing import AsyncGenerator, Awaitable, Any

import pytest
from redis.asyncio import Redis as AsyncRedis
from typing_extensions import Final, Protocol

from aio_redis_rate_limit import RateLimitError, RateSpec, rate_limit


class _LimitedSig(Protocol):
    def __call__(self, number: int = ...) -> Awaitable[int]:
        """We use this to assert the output."""


class _LimitedCallback(Protocol):
    def __call__(
        self,
        requests: int = ...,
        seconds: int = ...,
    ) -> _LimitedSig:
        """We use this callback to construct `limited` test function."""


_LIMIT: Final = 5
_SECONDS: Final = 1


@pytest.fixture()
async def redis() -> 'AsyncRedis[Any]':
    """Creates an async redis client."""
    return AsyncRedis.from_url(
        'redis://{0}:6379'.format(os.environ.get('REDIS_HOST', 'localhost')),
    )


@pytest.fixture(autouse=True)
async def _clear_redis(redis: 'AsyncRedis[Any]') -> AsyncGenerator[None, None]:
    """This fixture is needed to be sure that test start with fresh redis."""
    yield
    await redis.flushdb()


@pytest.fixture()
def limited(redis: 'AsyncRedis[Any]') -> _LimitedCallback:
    """Fixture to construct rate limited functions."""
    def factory(
        requests: int = _LIMIT,
        seconds: int = _SECONDS,
    ) -> _LimitedSig:
        @rate_limit(
            rate_spec=RateSpec(requests=requests, seconds=seconds),
            backend=redis,
        )
        async def decorator(index: int = 0) -> int:
            return index
        return decorator  # type: ignore[return-value]
    return factory


@pytest.mark.repeat(5)
async def test_correct(limited: _LimitedCallback) -> None:
    """Ensure that coroutine under limit always works correctly."""
    function = limited()
    for attempt in range(_LIMIT):
        assert await function(attempt) == attempt

    # Next attempt will raise:
    with pytest.raises(RateLimitError):
        await function()

test_correct_frozen = pytest.mark.freeze_time('2020-02-03')(test_correct)


@pytest.mark.parametrize(('limit', 'seconds'), [
    (_LIMIT, _SECONDS),
    (5, 2),
    (3, 3),
    (1, 2),
])
async def test_with_sleep(
    limited: _LimitedCallback,
    limit: int,
    seconds: int,
) -> None:
    """Ensure that when time passes, limit is restored."""
    function = limited(seconds=seconds, requests=limit)
    for attempt in range(limit):
        assert await function(attempt) == attempt

    # Next attempt will raise:
    with pytest.raises(RateLimitError):
        await function()

    # Sleep for a while:
    await asyncio.sleep(seconds)

    # Next attempt will not raise, since some time has passed:
    await function()


@pytest.mark.repeat(3)
async def test_gather_correct(limited: _LimitedCallback) -> None:
    """Ensure that several gathered coroutines do respect the rate limit."""
    function = limited()

    assert await asyncio.gather(*[
        function(attempt)
        for attempt in range(_LIMIT)
    ]) == [0, 1, 2, 3, 4]


@pytest.mark.repeat(3)
async def test_gather_limited(limited: _LimitedCallback) -> None:
    """Ensure gathered coroutines can be rate limited."""
    function = limited()

    with pytest.raises(RateLimitError):
        await asyncio.gather(*[
            function(attempt)
            for attempt in range(_LIMIT + 1)
        ])


@pytest.mark.repeat(5)
async def test_ten_reqs_in_two_secs(
    limited: _LimitedCallback,
    freezer,
) -> None:
    """Ensure that several gathered coroutines do respect the rate limit."""
    function = limited(requests=10, seconds=2)

    # At first, try 5 requests, a half:
    for attempt in range(5):
        await function(attempt)

    # Now, let's move time to the next second:
    freezer.move_to(dt.timedelta(seconds=1))

    # Other 5 should be fine:
    for attempt2 in range(5):
        await function(attempt2)

    # This one will fail:
    with pytest.raises(RateLimitError):
        await function()


@pytest.mark.repeat(5)
async def test_ten_reqs_in_two_secs2(
    limited: _LimitedCallback,
    freezer,
) -> None:
    """Ensure that several gathered coroutines do respect the rate limit."""
    function = limited(requests=10, seconds=2)

    # Or just consume all:
    for attempt in range(10):
        await function(attempt)

    # This one will fail:
    with pytest.raises(RateLimitError):
        await function()

    # Now, let's move time to the next second:
    freezer.move_to(dt.timedelta(seconds=1))

    # This one will also fail:
    with pytest.raises(RateLimitError):
        await function()
