from fastapi import WebSocket, WebSocketDisconnect
from .config import settings
import asyncio,json,uuid
try:
    import redis.asyncio as redis
except ImportError:
    redis=None

rooms={}
async def _local_signal(websocket,room_id):
    rooms.setdefault(room_id,set()).add(websocket)
    try:
        while True:
            message=await websocket.receive_text()
            for peer in list(rooms.get(room_id,set())):
                if peer is not websocket:
                    try: await peer.send_text(message)
                    except Exception: pass
    except Exception:
        pass
    finally:
        rooms.get(room_id,set()).discard(websocket)
        if not rooms.get(room_id): rooms.pop(room_id,None)

async def signal(websocket:WebSocket,room_id:str,allow_staff:bool=False):
    await websocket.accept()
    # Redis pub/sub is used when configured so handoff signaling works across API instances.
    if not settings.redis_url or redis is None:
        await _local_signal(websocket,room_id)
        return
    client_id=uuid.uuid4().hex
    channel=f"ago:call:{room_id}"
    r=redis.from_url(settings.redis_url,decode_responses=True)
    pubsub=r.pubsub()
    await pubsub.subscribe(channel)
    async def reader():
        try:
            async for item in pubsub.listen():
                if item.get("type")!="message": continue
                payload=json.loads(item["data"])
                if payload.get("sender")!=client_id:
                    await websocket.send_text(json.dumps(payload["message"]))
        except Exception:
            pass
    task=asyncio.create_task(reader())
    try:
        while True:
            message=await websocket.receive_text()
            payload=json.loads(message)
            if payload.get("type")=="staff_join" and not allow_staff:
                await websocket.send_text(json.dumps({"type":"error","message":"Staff signaling authorization required"}))
                continue
            await r.publish(channel,json.dumps({"sender":client_id,"message":payload}))
    except (WebSocketDisconnect,Exception):
        pass
    finally:
        task.cancel()
        try: await pubsub.unsubscribe(channel); await pubsub.close(); await r.close()
        except Exception: pass
