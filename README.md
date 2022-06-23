# aio-redis-rate-limit

[![wemake.services](https://img.shields.io/badge/%20-wemake.services-green.svg?label=%20&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAAABGdBTUEAALGPC%2FxhBQAAAAFzUkdCAK7OHOkAAAAbUExURQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP%2F%2F%2F5TvxDIAAAAIdFJOUwAjRA8xXANAL%2Bv0SAAAADNJREFUGNNjYCAIOJjRBdBFWMkVQeGzcHAwksJnAPPZGOGAASzPzAEHEGVsLExQwE7YswCb7AFZSF3bbAAAAABJRU5ErkJggg%3D%3D)](https://wemake-services.github.io)
[![Build Status](https://github.com/wemake-services/aio-redis-rate-limit/workflows/test/badge.svg?branch=master&event=push)](https://github.com/wemake-services/aio-redis-rate-limit/actions?query=workflow%3Atest)
[![codecov](https://codecov.io/gh/wemake-services/aio-redis-rate-limit/branch/master/graph/badge.svg)](https://codecov.io/gh/wemake-services/aio-redis-rate-limit)
[![Python Version](https://img.shields.io/pypi/pyversions/aio-redis-rate-limit.svg)](https://pypi.org/project/aio-redis-rate-limit/)
[![wemake-python-styleguide](https://img.shields.io/badge/style-wemake-000000.svg)](https://github.com/wemake-services/wemake-python-styleguide)

Rate limiter for async functions using Redis as a backend.


## Features

- Small and simple
- Can be used as a decorator or as a context manager
- Can be used for both clients and servers
- Works with `asyncio`
- Works with any amount of processes
- Free of race-conditions (hopefully!)
- Fully typed with annotations and checked with mypy, [PEP561 compatible](https://www.python.org/dev/peps/pep-0561/)


## Installation

```bash
pip install aio-redis-rate-limit
```


## Example

```python
>>> from asyncio_redis_rate_limit import rate_limit, RateSpec
>>> from redis.asyncio import Redis as AsyncRedis  # pip install redis

>>> redis = AsyncRedis.from_url('redis://localhost:6379')

>>> @rate_limit(
...    rate_spec=RateSpec(requests=1200, seconds=60),
...    backend=redis,
... )
... async def request() -> int:
...     ...   # Do something useful! Call this function as usual.

```

Or as a context manager:

```python
>>> from asyncio_redis_rate_limit import RateLimiter, RateSpec
>>> from redis.asyncio import Redis as AsyncRedis  # pip install redis

>>> redis = AsyncRedis.from_url('redis://localhost:6379')

>>> async def request() -> ...:
...     async with RateLimiter(
...         unique_key='api-name.com',
...         backend=redis,
...         rate_spec=RateSpec(requests=5, seconds=1),
...     ):
...         ...  # Do the request itself.

```


## License

[MIT](https://github.com/wemake-services/aio-redis-rate-limit/blob/master/LICENSE)


## Credits

This project was generated with [`wemake-python-package`](https://github.com/wemake-services/wemake-python-package). Current template version is: [1d63652fbb33ebe2f6d932f511b7f529a4ce2d2a](https://github.com/wemake-services/wemake-python-package/tree/1d63652fbb33ebe2f6d932f511b7f529a4ce2d2a). See what is [updated](https://github.com/wemake-services/wemake-python-package/compare/1d63652fbb33ebe2f6d932f511b7f529a4ce2d2a...master) since then.
