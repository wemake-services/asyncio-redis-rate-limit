import asyncio
import multiprocessing
import os
import time

import pytest
from typing_extensions import Final

from asyncio_redis_rate_limit import RateLimitError, RateSpec, rate_limit
from asyncio_redis_rate_limit.compat import (  # type: ignore  # noqa: WPS450
    HAS_REDIS,
    _AsyncRedis,
)

if not HAS_REDIS:
    pytest.skip('`redis` package is not installed', allow_module_level=True)

_redis: Final = _AsyncRedis.from_url(
    'redis://{0}:6379'.format(os.environ.get('REDIS_HOST', 'localhost')),
)
_event_loop: Final = asyncio.new_event_loop()
_LIMIT: Final = 5
_SECONDS: Final = 1


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    """Overriding `pytest-asyncio` fixture."""
    return _event_loop


@rate_limit(
    rate_spec=RateSpec(requests=_LIMIT, seconds=_SECONDS),
    backend=_redis,
    cache_prefix='mp-redis',
)
async def _limited(index: int) -> int:
    return index


def _worker(number: int) -> int:
    return _event_loop.run_until_complete(_limited(number))


def test_multiprocess(event_loop: asyncio.BaseEventLoop) -> None:
    """Ensure that `multiprocessing` works with limits."""
    with multiprocessing.Pool() as pool:
        reduced = pool.map(_worker, list(range(_LIMIT)))
    assert reduced == [0, 1, 2, 3, 4]

    time.sleep(_SECONDS)

    with multiprocessing.Pool() as pool2:
        with pytest.raises(RateLimitError):
            pool2.map(_worker, list(range(_LIMIT + 1)))
