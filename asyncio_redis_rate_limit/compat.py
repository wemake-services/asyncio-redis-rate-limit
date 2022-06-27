from typing import Any, Generic, TypeVar, Union

from typing_extensions import TypeAlias

_EmptyType = TypeVar('_EmptyType')

try:  # noqa: WPS229  # pragma: no cover
    from redis.asyncio.client import Pipeline as _AsyncPipeline  # noqa: WPS433
    from redis.asyncio.client import Redis as _AsyncRedis  # noqa: WPS433

    HAS_REDIS = True
except ImportError:
    class _AsyncPipeline(  # type: ignore  # noqa: WPS306, WPS440
        Generic[_EmptyType],
    ):
        """Fallback pipeline type if `redis` is not installed."""

    class _AsyncRedis(  # type: ignore  # noqa: WPS306, WPS440
        Generic[_EmptyType],
    ):
        """Fallback redis type if `redis` is not installed."""

    HAS_REDIS = False

try:  # noqa: WPS229  # pragma: no cover
    from aioredis.client import Pipeline as _AIOPipeline  # noqa: WPS433
    from aioredis.client import Redis as _AIORedis  # noqa: WPS433

    HAS_AIOREDIS = True
except ImportError:
    class _AIOPipeline:  # type: ignore  # noqa: WPS306, WPS440
        """Fallback pipeline type if `aioredis` is not installed."""

    class _AIORedis:  # type: ignore  # noqa: WPS306, WPS440
        """Fallback redis type if `aioredis` is not installed."""

    HAS_AIOREDIS = False

AnyPipeline: TypeAlias = Union['_AsyncPipeline[Any]', _AIOPipeline]
AnyRedis: TypeAlias = Union['_AsyncRedis[Any]', _AIORedis]


def pipeline_expire(
    pipeline: Any,
    cache_key: str,
    seconds: int,
) -> AnyPipeline:
    """Compatibility mode for `.expire(..., nx=True)` command."""
    if isinstance(pipeline, _AsyncPipeline):
        return pipeline.expire(cache_key, seconds, nx=True)  # type: ignore
    # `aioredis` somehow does not have this boolean argument in `.expire`,
    # so, we use `EXPIRE` directly with `NX` flag.
    return pipeline.execute_command(  # type: ignore
        'EXPIRE',
        cache_key,
        seconds,
        'NX',
    )
