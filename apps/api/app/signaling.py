from fastapi import WebSocket, WebSocketDisconnect
from .config import settings
import asyncio
import json
import uuid

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

rooms = {}


# ---------------------------------------------------------------------------
# WebRTC drop recovery hook
# ---------------------------------------------------------------------------

def _do_trigger_recovery(room_id: str, reason: str = "ws_disconnect"):
    """Open a fresh DB session, find the CallRecord, trigger recovery.

    Runs synchronously inside the event loop callback. Never raises.
    """
    try:
        from .db import SessionLocal
        from .models_growth import CallRecord
        from .models import Tenant
        from .webrtc_recovery import start_recovery

        db = SessionLocal()
        try:
            record = db.query(CallRecord).filter_by(room_id=room_id).first()
            if record is None:
                return
            if record.status in ("ended", "completed", "missed"):
                return
            tenant = db.query(Tenant).filter_by(id=record.tenant_id).first()
            if tenant is None:
                return
            start_recovery(db, tenant, record, reason=reason)
        finally:
            db.close()
    except Exception:
        # Never let recovery failures affect signaling.
        pass


async def _trigger_recovery_async(room_id: str, reason: str = "ws_disconnect"):
    """Fire-and-forget async wrapper. Schedules on the running loop."""
    try:
        import asyncio
        asyncio.get_event_loop().call_soon(_do_trigger_recovery, room_id, reason)
    except Exception:
        pass


async def _local_signal(websocket, room_id, allow_staff, allow_customer, conn_id):
    room = rooms.setdefault(room_id, {"seats": {}, "connections": {}, "ended": False})
    room["connections"][conn_id] = websocket
    role = None
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if not isinstance(message, dict):
                continue
            msg_type = message.get("type")

            if msg_type == "join":
                requested = "staff" if message.get("role") == "staff" else "customer"
                if requested == "staff" and not allow_staff:
                    await websocket.send_json({"type": "rejected", "reason": "staff_auth_required"})
                    continue
                if requested == "customer" and not allow_customer:
                    await websocket.send_json({"type": "rejected", "reason": "customer_token_required"})
                    continue
                if room["ended"]:
                    await websocket.send_json({"type": "ended"})
                    continue

                existing = room["seats"].get(requested)
                if existing and existing != conn_id:
                    await websocket.send_json({"type": "rejected", "reason": "seat_taken"})
                    continue

                role = requested
                room["seats"][role] = conn_id
                await websocket.send_json({"type": "joined", "role": role})

                other = "staff" if role == "customer" else "customer"
                if room["seats"].get(other):
                    peer = room["connections"].get(room["seats"][other])
                    if peer:
                        await peer.send_json({"type": "peer_joined"})
                    customer_conn = room["connections"].get(room["seats"].get("customer"))
                    if customer_conn:
                        await customer_conn.send_json({"type": "ready"})
                continue

            if not role or room["seats"].get(role) != conn_id:
                continue

            if msg_type == "signal":
                data = message.get("data")
                if not isinstance(data, dict) or len(json.dumps(data)) > 20000:
                    continue
                other = "staff" if role == "customer" else "customer"
                peer = room["connections"].get(room["seats"].get(other))
                if peer:
                    await peer.send_json({"type": "signal", "data": data})

            elif msg_type == "hangup":
                room["ended"] = True
                for peer in list(room["connections"].values()):
                    try:
                        await peer.send_json({"type": "ended"})
                    except Exception:
                        pass
                break

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        ended_normally = bool(room.get("ended"))
        was_customer = (role == "customer")

        room["connections"].pop(conn_id, None)
        if role and room["seats"].get(role) == conn_id:
            room["seats"].pop(role, None)
        if not room["connections"]:
            rooms.pop(room_id, None)

        # Trigger recovery if a customer dropped without a clean hangup.
        if was_customer and not ended_normally:
            try:
                import asyncio as _asyncio
                _asyncio.get_event_loop().call_soon(
                    _do_trigger_recovery, room_id, "ws_disconnect_local"
                )
            except Exception:
                pass


async def signal(websocket: WebSocket, room_id: str, allow_staff: bool = False, allow_customer: bool = False):
    await websocket.accept()

    # Base44's two-seat signaling model: exactly one customer and one staff seat.
    # Our signed short-lived room tokens remain the authorization boundary.
    if not settings.redis_url or redis is None:
        conn_id = uuid.uuid4().hex
        await _local_signal(websocket, room_id, allow_staff, allow_customer, conn_id)
        return

    client_id = uuid.uuid4().hex
    channel = f"ago:call:{room_id}"
    r = redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    role = None
    seat_key = None

    async def reader():
        try:
            async for item in pubsub.listen():
                if item.get("type") != "message":
                    continue
                payload = json.loads(item["data"])
                if payload.get("sender") == client_id:
                    continue
                target = payload.get("target_role")
                if target and target != role:
                    continue
                await websocket.send_text(json.dumps(payload["message"]))
        except Exception:
            pass

    task = asyncio.create_task(reader())

    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if not isinstance(message, dict):
                continue
            msg_type = message.get("type")

            if msg_type == "join":
                requested = "staff" if message.get("role") == "staff" else "customer"

                if requested == "staff" and not allow_staff:
                    await websocket.send_text(json.dumps({"type": "rejected", "reason": "staff_auth_required"}))
                    continue
                if requested == "customer" and not allow_customer:
                    await websocket.send_text(json.dumps({"type": "rejected", "reason": "customer_token_required"}))
                    continue

                if await r.get(f"ago:call:{room_id}:ended"):
                    await websocket.send_text(json.dumps({"type": "ended"}))
                    continue

                key = f"ago:call:{room_id}:seat:{requested}"
                acquired = await r.set(key, client_id, nx=True, ex=3600)
                if not acquired:
                    await websocket.send_text(json.dumps({"type": "rejected", "reason": "seat_taken"}))
                    continue

                role = requested
                seat_key = key
                await websocket.send_text(json.dumps({"type": "joined", "role": role}))

                other = "staff" if role == "customer" else "customer"
                other_id = await r.get(f"ago:call:{room_id}:seat:{other}")
                if other_id:
                    await r.publish(
                        channel,
                        json.dumps({
                            "sender": client_id,
                            "target_role": other,
                            "message": {"type": "peer_joined"},
                        }),
                    )
                    if role == "customer":
                        await websocket.send_text(json.dumps({"type": "ready"}))
                    else:
                        await r.publish(
                            channel,
                            json.dumps({
                                "sender": client_id,
                                "target_role": "customer",
                                "message": {"type": "ready"},
                            }),
                        )
                continue

            if not role:
                continue

            if msg_type == "signal":
                data = message.get("data")
                if not isinstance(data, dict) or len(json.dumps(data)) > 20000:
                    continue
                other = "staff" if role == "customer" else "customer"
                target_id = await r.get(f"ago:call:{room_id}:seat:{other}")
                if target_id:
                    await r.publish(
                        channel,
                        json.dumps({
                            "sender": client_id,
                            "target_role": other,
                            "message": {"type": "signal", "data": data},
                        }),
                    )

            elif msg_type == "hangup":
                await r.set(f"ago:call:{room_id}:ended", "1", ex=3600)
                await r.publish(
                    channel,
                    json.dumps({
                        "sender": client_id,
                        "message": {"type": "ended"},
                    }),
                )
                break

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        # WebRTC drop recovery hook - fires when a customer disconnects
        # without a clean hangup message.
        try:
            if role == "customer" and not (await r.get(f"ago:call:{room_id}:ended")):
                import asyncio as _asyncio
                _asyncio.get_event_loop().call_soon(
                    _do_trigger_recovery, room_id, "ws_disconnect_redis"
                )
        except Exception:
            pass
        task.cancel()
        if seat_key:
            try:
                current = await r.get(seat_key)
                if current == client_id:
                    await r.delete(seat_key)
            except Exception:
                pass
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await r.close()
        except Exception:
            pass
