from redis.asyncio import Redis


async def increment_window_counter(
    redis: Redis,
    *,
    key: str,
    window_seconds: int,
) -> int:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return int(count)


async def mark_alert_dedup(
    redis: Redis,
    *,
    fingerprint: str,
    ttl_seconds: int,
) -> bool:
    key = f"alert_dedup:{fingerprint}"
    return bool(await redis.set(key, "1", ex=ttl_seconds, nx=True))
