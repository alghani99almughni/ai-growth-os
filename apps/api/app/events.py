from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from .config import settings

try:
    import redis.asyncio as redis_async
    import redis as redis_sync
except ImportError:
    redis_async = None
    redis_sync = None

_local_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

async def publish_event(tenant_id: str, event_type: str, data: dict, *, context_token: str | None = None) -> None:
    payload = {
        "id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "type": event_type,
        "context_token": context_token,
        "data": data,
    }
    message = json.dumps(payload, default=str)
    channel = f"ago:events:{tenant_id}"

    if not settings.redis_url or redis_async is None:
        for queue in list(_local_subscribers.get(channel, set())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    if settings.redis_url and redis_async is not None:
        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.publish(channel, message)
        finally:
            await client.close()

def publish_event_sync(tenant_id: str, event_type: str, data: dict, *, context_token: str | None = None) -> None:
    payload = {
        "id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "type": event_type,
        "context_token": context_token,
        "data": data,
    }
    message = json.dumps(payload, default=str)
    channel = f"ago:events:{tenant_id}"

    if settings.redis_url and redis_sync is not None:
        client = redis_sync.from_url(settings.redis_url, decode_responses=True)
        try:
            client.publish(channel, message)
        finally:
            client.close()

async def subscribe_events(tenant_id: str):
    channel = f"ago:events:{tenant_id}"
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _local_subscribers[channel].add(queue)

    redis_client = None
    pubsub = None
    task = None
    redis_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    async def redis_reader():
        if not settings.redis_url or redis_async is None:
            return
        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        ps = client.pubsub()
        await ps.subscribe(channel)
        try:
            async for item in ps.listen():
                if item.get("type") == "message":
                    try:
                        redis_queue.put_nowait(json.loads(item["data"]))
                    except asyncio.QueueFull:
                        pass
        finally:
            await ps.close()
            await client.close()

    if settings.redis_url and redis_async is not None:
        task = asyncio.create_task(redis_reader())

    try:
        while True:
            local_task = asyncio.create_task(queue.get())
            remote_task = asyncio.create_task(redis_queue.get())
            done, pending = await asyncio.wait(
                {local_task, remote_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()
            yield next(iter(done)).result()
    finally:
        _local_subscribers[channel].discard(queue)
        if not _local_subscribers[channel]:
            _local_subscribers.pop(channel, None)
        if task:
            task.cancel()
