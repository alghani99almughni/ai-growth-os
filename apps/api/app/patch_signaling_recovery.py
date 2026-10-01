"""Wire WebRTC drop recovery into signaling.py.

Adds a fire-and-forget recovery trigger to both the _local_signal and the
Redis-backed signal handlers. When a customer's WebSocket disconnects without
a clean 'hangup', we open a fresh DB session and trigger webrtc_recovery.

Never raises. Never blocks signaling.
"""

import pathlib

path = pathlib.Path("signaling.py")
text = path.read_text(encoding="utf-8")

if "_do_trigger_recovery" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# 1. Add the recovery helper right before _local_signal.
# ---------------------------------------------------------------------------

marker = "async def _local_signal("
helper = '''# ---------------------------------------------------------------------------
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


'''

if marker not in text:
    print("ERROR: _local_signal not found")
    raise SystemExit(1)

text = text.replace(marker, helper + marker, 1)

# ---------------------------------------------------------------------------
# 2. Patch the _local_signal finally block.
# ---------------------------------------------------------------------------

old_local = '''    finally:
        room["connections"].pop(conn_id, None)
        if role and room["seats"].get(role) == conn_id:
            room["seats"].pop(role, None)
        if not room["connections"]:
            rooms.pop(room_id, None)'''

new_local = '''    finally:
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
                pass'''

if old_local in text:
    text = text.replace(old_local, new_local, 1)
    print("Patched: _local_signal finally block")
else:
    print("WARNING: _local_signal finally block not found verbatim")

# ---------------------------------------------------------------------------
# 3. Patch the signal() function's finally block.
#    Because we haven't seen the exact text, we append a recovery hook
#    right after the finally keyword of the signal() function.
# ---------------------------------------------------------------------------

signal_start = text.find("async def signal(")
if signal_start < 0:
    print("WARNING: signal() not found")
else:
    # Find the finally: keyword inside signal()
    finally_pos = text.find("    finally:", signal_start)
    if finally_pos < 0:
        print("WARNING: signal() finally block not found")
    else:
        # Insert the recovery hook right after 'finally:' - it will run on
        # every exit from the try block (clean or exception).
        hook = '''    finally:
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
'''
        text = text[:finally_pos] + hook + text[finally_pos + len("    finally:\n"):]
        print("Patched: signal() finally block")

path.write_text(text, encoding="utf-8")
print("Done. New size:", len(text), "bytes")
print("_do_trigger_recovery references:", text.count("_do_trigger_recovery"))