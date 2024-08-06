import asyncio
import os
from typing import AsyncGenerator, Awaitable, cast

import pytest
from typing_extensions import Final, Protocol

from asyncio_redis_rate_limit import RateLimitError, RateSpec, rate_limit
from asyncio_redis_rate_limit.compat import (  # type: ignore  # noqa: WPS450
    HAS_AIOREDIS,
    HAS_REDIS,
    AnyRedis,
    _AIORedis,
    _AsyncRedis,
)


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


@pytest.fixture(params=[_AsyncRedis, _AIORedis])
async def redis(request: pytest.FixtureRequest) -> AnyRedis:
    """Creates an async redis client."""
    if issubclass(request.param, _AsyncRedis) and not HAS_REDIS:
        pytest.skip('`redis` is not installed')
    elif issubclass(request.param, _AIORedis) and not HAS_AIOREDIS:
        pytest.skip('`aioredis` is not installed')

    return cast(AnyRedis, request.param.from_url(
        'redis://{0}:6379'.format(os.environ.get('REDIS_HOST', 'localhost')),
    ))


@pytest.fixture(autouse=True)
async def _clear_redis(redis: AnyRedis) -> AsyncGenerator[None, None]:
    """This fixture is needed to be sure that test start with fresh redis."""
    yield
    await redis.flushdb()


@pytest.fixture
def limited(redis: AnyRedis) -> _LimitedCallback:
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

#: Freezing time on a client won't help, server's time is important.
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
    await asyncio.sleep(seconds + 0.5)  # for extra safety

    # Next attempt will not raise, since some time has passed:
    await function()


async def test_different_functions(
    limited: _LimitedCallback,
    redis: AnyRedis,
) -> None:
    """Ensure that unrelated functions are unrelated."""
    @rate_limit(
        rate_spec=RateSpec(requests=5, seconds=1),
        backend=redis,
    )
    async def factory(index: int = 0) -> int:
        return index

    for attempt in range(_LIMIT):
        await factory(attempt)

    # Next attempt will raise:
    with pytest.raises(RateLimitError):
        await factory()

    # Unrelated function should be fine:
    factory2 = limited()
    for attempt2 in range(5):
        await factory2(attempt2)

    # Next attempt will raise:
    with pytest.raises(RateLimitError):
        await factory2()


async def test_different_prefixes(redis: AnyRedis) -> None:
    """Ensure that different prefixes work for the same function."""
    async def factory(index: int = 0) -> int:
        return index

    limited1 = rate_limit(
        rate_spec=RateSpec(requests=5, seconds=1),
        backend=redis,
        cache_prefix='one',
    )(factory)

    for attempt in range(_LIMIT):
        await limited1(attempt)

    # Next attempt will raise:
    with pytest.raises(RateLimitError):
        await limited1()

    # Different prefix should be fine:
    limited2 = rate_limit(
        rate_spec=RateSpec(requests=5, seconds=1),
        backend=redis,
        cache_prefix='two',
    )(factory)

    for attempt2 in range(5):
        await limited2(attempt2)

    # Next attempt will raise:
    with pytest.raises(RateLimitError):
        await limited2()


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
) -> None:
    """Ensure that several gathered coroutines do respect the rate limit."""
    function = limited(requests=10, seconds=2)

    # At first, try 5 requests, a half:
    for attempt in range(5):
        await function(attempt)

    # Now, let's move time to the next second:
    await asyncio.sleep(1)

    # Other 5 should be fine:
    for attempt2 in range(5):
        await function(attempt2)

    # This one will fail:
    with pytest.raises(RateLimitError):
        await function()


@pytest.mark.repeat(5)
async def test_ten_reqs_in_two_secs2(
    limited: _LimitedCallback,
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
    await asyncio.sleep(1)

    # This one will also fail:
    with pytest.raises(RateLimitError):
        await function()

    # Next attempts will pass:
    await asyncio.sleep(1 + 0.5)
    await function()


class _Counter:
    def __init__(self) -> None:
        self.count = 0

    async def increment(self) -> None:
        self.count += 1


@pytest.mark.repeat(5)
async def test_that_rate_limit_do_not_cancel_others(redis: AnyRedis) -> None:
    """Ensure that when rate limit is hit, we still execute other requests."""
    counter = _Counter()
    limited = rate_limit(
        rate_spec=RateSpec(requests=_LIMIT, seconds=2),
        backend=redis,
        cache_prefix='one',
    )(counter.increment)

    for attempt in range(_LIMIT + 1):
        if attempt == _LIMIT:
            with pytest.raises(RateLimitError):
                await limited()
        else:
            await limited()

    # But, we still do this work while rate limit is not met:
    assert counter.count == _LIMIT
