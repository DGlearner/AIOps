from redis.asyncio import Redis

from crossst.core.config import get_settings

# 负责 Redis 连接管理

settings = get_settings()

redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


async def get_redis() -> Redis:
    return redis_client


async def check_redis() -> bool:
    return await redis_client.ping()


async def close_redis() -> None:
    await redis_client.aclose()
