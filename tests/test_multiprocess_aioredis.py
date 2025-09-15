import asyncio
import multiprocessing
import os
import time
from typing import Final

import pytest

from asyncio_redis_rate_limit import RateLimitError, RateSpec, rate_limit
from asyncio_redis_rate_limit.compat import (  # type: ignore
    HAS_AIOREDIS,
    _AIORedis,  # noqa: PLC2701
)

if not HAS_AIOREDIS:
    pytest.skip('`aioredis` package is not installed', allow_module_level=True)

_redis: Final = _AIORedis.from_url(
    'redis://{}:6379'.format(os.environ.get('REDIS_HOST', 'localhost')),
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
    cache_prefix='mp-aioredis',
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

    with multiprocessing.Pool() as pool2, pytest.raises(RateLimitError):
        pool2.map(_worker, list(range(_LIMIT + 1)))
