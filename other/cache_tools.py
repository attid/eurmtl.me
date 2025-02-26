import asyncio
from functools import wraps
from time import time
from typing import Optional, Any


class AsyncTTLCache:
    def __init__(self, ttl_seconds: int, maxsize: int = 1):
        self.ttl_seconds = ttl_seconds
        self.maxsize = maxsize
        self.cache = {}

    async def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            timestamp, value = self.cache[key]
            if time() - timestamp < self.ttl_seconds:
                return value
            else:
                del self.cache[key]
        return None

    async def set(self, key: str, value: Any) -> None:
        if value is None:
            return

        if len(self.cache) >= self.maxsize:
            # При maxsize=1 просто очищаем кэш
            self.cache.clear()

        self.cache[key] = (time(), value)


def async_cache_with_ttl(ttl_seconds: int, maxsize: int = 1):
    cache = AsyncTTLCache(ttl_seconds, maxsize)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = str(args) + str(kwargs)

            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)

            await cache.set(cache_key, result)

            return result

        return wrapper

    return decorator


# Примеры использования:

# С дефолтным maxsize=1
@async_cache_with_ttl(ttl_seconds=3600)
async def get_fund_signers():
    print('real call')
    return 'data'


# Тестирование
async def test():
    result1 = await get_fund_signers()
    print(result1)

    # Повторный вызов должен взять из кэша
    result2 = await get_fund_signers()
    print(result2)


if __name__ == "__main__":
    asyncio.run(test())
