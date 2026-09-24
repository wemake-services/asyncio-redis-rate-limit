import asyncio
import os
from typing import Final

import pytest

from asyncio_redis_rate_limit import RateLimitError, RateSpec, rate_limit
from asyncio_redis_rate_limit.compat import (  # type: ignore
    HAS_REDIS,
    _AsyncRedis,  # ruff:ignore[import-private-name]
)

if not HAS_REDIS:
    pytest.skip('`redis` package is not installed', allow_module_level=True)

_redis: Final = _AsyncRedis.from_url(
    'redis://{}:6379'.format(os.environ.get('REDIS_HOST', 'localhost')),
)
_LIMIT: Final = 10
_TOTAL: Final = 100


@rate_limit(
    rate_spec=RateSpec(requests=_LIMIT, seconds=60),
    backend=_redis,
    cache_prefix='concurrent-within-loop',
)
async def _limited(index: int) -> int:
    return index


async def test_concurrent_calls_enforce_limit() -> None:
    """Regression test.

    A shared-nothing per-call lock cannot serialize concurrent calls from
    the *same* event loop either (each call builds its own fresh
    `RateLimiter`/lock), so correctness must come from the redis pipeline's
    own atomicity, not the lock. Admitted/denied counts must match the
    configured limit regardless.
    """
    gather_outcomes = await asyncio.gather(
        *(_limited(attempt) for attempt in range(_TOTAL)),
        return_exceptions=True,
    )

    admitted = [
        outcome
        for outcome in gather_outcomes
        if not isinstance(outcome, BaseException)
    ]
    denied = [
        outcome
        for outcome in gather_outcomes
        if isinstance(outcome, RateLimitError)
    ]
    unexpected_errors = [
        outcome
        for outcome in gather_outcomes
        if isinstance(outcome, BaseException)
        and not isinstance(outcome, RateLimitError)
    ]

    assert not unexpected_errors
    assert len(admitted) == _LIMIT
    assert len(denied) == _TOTAL - _LIMIT
