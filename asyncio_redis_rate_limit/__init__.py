import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from functools import wraps
from types import TracebackType
from typing import NamedTuple, TypeAlias, TypeVar

from typing_extensions import ParamSpec, final

from asyncio_redis_rate_limit.compat import (
    AnyPipeline,
    AnyRedis,
    pipeline_expire,
)

#: These aliases makes our code more readable.
_Seconds: TypeAlias = int

_ResultT = TypeVar('_ResultT')
_ParamsT = ParamSpec('_ParamsT')

_CoroutineFunction: TypeAlias = Callable[_ParamsT, Awaitable[_ResultT]]

_RateLimiterT = TypeVar('_RateLimiterT', bound='RateLimiter')


@final
class RateLimitError(Exception):
    """We raise this error when rate limit is hit."""


@final
class RateSpec(NamedTuple):
    """
    Specifies the amount of requests can be made in the time frame in seconds.

    It is much nicier than using a custom string format like ``100/1s``.
    """

    requests: int
    seconds: _Seconds


class RateLimiter:
    """Implements rate limiting."""

    __slots__ = (
        '_backend',
        '_cache_prefix',
        '_lock',
        '_rate_spec',
        '_unique_key',
    )

    def __init__(
        self,
        unique_key: str,
        rate_spec: RateSpec,
        backend: AnyRedis,
        *,
        cache_prefix: str,
    ) -> None:
        """In the future other backends might be supported as well."""
        self._unique_key = unique_key
        self._rate_spec = rate_spec
        self._backend = backend
        self._cache_prefix = cache_prefix
        self._lock = asyncio.Lock()

    async def __aenter__(self: _RateLimiterT) -> _RateLimiterT:
        """
        Async context manager API.

        Before this object will be used, we call ``self._acquire`` to be sure
        that we can actually make any actions in this time frame.
        """
        await self._acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Do nothing. We need this to ``__aenter__`` to work."""

    async def redis_version(self):
        version = await self._backend.info(section='SERVER')
        return version['redis_version']

    # Private API:

    async def _acquire(self) -> None:
        cache_key = self._make_cache_key(
            unique_key=self._unique_key,
            rate_spec=self._rate_spec,
            cache_prefix=self._cache_prefix,
        )
        pipeline = self._backend.pipeline()

        async with self._lock:
            redis_version = await self.redis_version()

            if int(redis_version.split('.')[0]) < 7:
                current_rate, *_ = await pipeline.incr(cache_key).execute()
                if current_rate == 1:
                    await pipeline.expire(
                        cache_key,
                        self._rate_spec.seconds
                    ).execute()
            else:
                current_rate = await self._run_pipeline(cache_key, pipeline)
            # This looks like a coverage error on 3.10:
            if current_rate > self._rate_spec.requests:  # pragma: no cover
                raise RateLimitError('Rate limit is hit', current_rate)

    async def _run_pipeline(
        self,
        cache_key: str,
        pipeline: AnyPipeline,
    ) -> int:
        # https://redis.io/commands/incr/#pattern-rate-limiter-1
        current_rate, _ = await pipeline_expire(
            pipeline.incr(cache_key),
            cache_key,
            self._rate_spec.seconds,
        ).execute()
        return current_rate  # type: ignore[no-any-return]

    def _make_cache_key(
        self,
        unique_key: str,
        rate_spec: RateSpec,
        cache_prefix: str,
    ) -> str:
        parts = ''.join([unique_key, str(rate_spec)])
        return (
            cache_prefix
            + hashlib.md5(  # noqa: S324
                parts.encode('utf-8'),
            ).hexdigest()
        )


def rate_limit(  # noqa: WPS320
    rate_spec: RateSpec,
    backend: AnyRedis,
    *,
    cache_prefix: str = 'aio-rate-limit',
) -> Callable[
    [_CoroutineFunction[_ParamsT, _ResultT]],
    _CoroutineFunction[_ParamsT, _ResultT],
]:
    """
    Rate limits a function.

    Code example:

      .. code:: python

        >>> from asyncio_redis_rate_limit import rate_limit, RateSpec
        >>> from redis.asyncio import Redis as AsyncRedis

        >>> redis = AsyncRedis.from_url('redis://localhost:6379')

        >>> @rate_limit(
        ...     rate_spec=RateSpec(requests=1200, seconds=60),
        ...     backend=redis,
        ... )
        ... async def request() -> int: ...  # Do something

    """

    def decorator(
        function: _CoroutineFunction[_ParamsT, _ResultT],
    ) -> _CoroutineFunction[_ParamsT, _ResultT]:
        @wraps(function)
        async def factory(
            *args: _ParamsT.args,
            **kwargs: _ParamsT.kwargs,
        ) -> _ResultT:
            module_name = getattr(function, '__module__', '__missing_module__')
            async with RateLimiter(
                unique_key=f'{module_name}.{function.__qualname__}',
                backend=backend,
                rate_spec=rate_spec,
                cache_prefix=cache_prefix,
            ):
                return await function(*args, **kwargs)

        return factory

    return decorator
