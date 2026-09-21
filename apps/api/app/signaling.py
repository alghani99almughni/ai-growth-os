from fastapi import WebSocket
import asyncio
rooms={}
async def signal(websocket:WebSocket,room_id:str):
    await websocket.accept()
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
