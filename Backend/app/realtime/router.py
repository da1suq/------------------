from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .auth_stub import User, get_current_user, user_from_token  # TODO(B1): заменить на app.auth
from .hub import HubError, hub

router = APIRouter(tags=["rooms"])


class CreateRoomIn(BaseModel):
    mode: str = Field(pattern="^(duel|team)$")
    task_ids: list[int] = Field(min_length=1)
    duration_minutes: int = Field(default=30, ge=1, le=600)


class JoinIn(BaseModel):
    invite_token: str


def _http(e: HubError) -> HTTPException:
    codes = {"not_found": 404, "forbidden": 403, "room_full": 409, "already_started": 409}
    return HTTPException(codes.get(e.code, 400), {"code": e.code, "message": e.message})


@router.post("/rooms")
def create_room(body: CreateRoomIn, user: User = Depends(get_current_user)):
    try:
        room = hub.create_room(user.id, user.name, body.mode, body.task_ids, body.duration_minutes)
    except HubError as e:
        raise _http(e)
    return {"room_id": room.id, "invite_token": room.invite_token,
            "invite_url": f"/join/{room.invite_token}"}


@router.post("/rooms/join")
def join_room(body: JoinIn, user: User = Depends(get_current_user)):
    try:
        room = hub.join_by_token(body.invite_token, user.id, user.name)
    except HubError as e:
        raise _http(e)
    return {"room_id": room.id}


def _check_member(room_id: int, user: User):
    try:
        room = hub.get_room(room_id)
    except HubError as e:
        raise _http(e)
    if user.id not in room.participants:
        raise HTTPException(403, {"code": "forbidden", "message": "not a participant"})
    return room


@router.get("/rooms/{room_id}")
def get_room(room_id: int, user: User = Depends(get_current_user)):
    return hub.snapshot(_check_member(room_id, user))


@router.get("/rooms/{room_id}/result")
def get_result(room_id: int, user: User = Depends(get_current_user)):
    room = _check_member(room_id, user)
    if room.status != "finished":
        raise HTTPException(409, {"code": "not_finished", "message": "contest is not finished"})
    return hub.result(room)


@router.websocket("/ws/rooms/{room_id}")
async def room_ws(ws: WebSocket, room_id: int, token: str = ""):
    user = user_from_token(token)
    if user is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        await hub.connect(room_id, user.id, ws)
    except HubError as e:
        await ws.send_json({"type": "error", "data": {"code": e.code, "message": e.message}})
        await ws.close(code=4403 if e.code == "forbidden" else 4404)
        return
    try:
        while True:
            msg = await ws.receive_json()
            await hub.handle_message(room_id, user.id, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(room_id, user.id, ws)
