"""Комнаты и рассылка событий в реальном времени.

Не зависит от FastAPI: сокет — любой объект с `async send_json(dict)`.
Состояние хранится в памяти процесса (достаточно для прототипа).
TODO(persist): писать rooms / room_participants в БД, чтобы пережить рестарт.
"""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from .scoring import Attempt, Standing, compute_standing, decide_winner

GRACE_SECONDS = 60
MAX_PARTICIPANTS = 2


class WS(Protocol):
    async def send_json(self, data: dict) -> None: ...


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


@dataclass
class Participant:
    user_id: int
    name: str
    ready: bool = False
    online: bool = False
    left: bool = False


@dataclass
class Room:
    id: int
    mode: str  # duel | team
    task_ids: list[int]
    duration_minutes: int
    invite_token: str
    owner_id: int
    status: str = "waiting"  # waiting | running | finished
    started_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    winner: Optional[object] = None  # user_id | "team" | None
    finish_reason: Optional[str] = None
    participants: dict[int, Participant] = field(default_factory=dict)
    attempts: list[Attempt] = field(default_factory=list)
    sockets: dict[int, WS] = field(default_factory=dict)
    grace_tasks: dict[int, asyncio.Task] = field(default_factory=dict)
    timer_task: Optional[asyncio.Task] = None


class HubError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class Hub:
    def __init__(self, grace_seconds: int = GRACE_SECONDS):
        self.rooms: dict[int, Room] = {}
        self._by_token: dict[str, int] = {}
        self._next_id = 1
        self.grace_seconds = grace_seconds

    # ---------- REST-уровень ----------
    def create_room(self, owner_id: int, owner_name: str, mode: str,
                    task_ids: list[int], duration_minutes: int) -> Room:
        if mode not in ("duel", "team"):
            raise HubError("bad_mode", "mode must be duel or team")
        if not task_ids:
            raise HubError("no_tasks", "task_ids must not be empty")
        room = Room(
            id=self._next_id, mode=mode, task_ids=list(task_ids),
            duration_minutes=duration_minutes,
            invite_token=secrets.token_urlsafe(8), owner_id=owner_id,
        )
        self._next_id += 1
        room.participants[owner_id] = Participant(owner_id, owner_name)
        self.rooms[room.id] = room
        self._by_token[room.invite_token] = room.id
        return room

    def join_by_token(self, token: str, user_id: int, name: str) -> Room:
        room = self.rooms.get(self._by_token.get(token, -1))
        if room is None:
            raise HubError("not_found", "invite not found")
        if user_id in room.participants:
            return room
        if room.status != "waiting":
            raise HubError("already_started", "contest already started")
        if len(room.participants) >= MAX_PARTICIPANTS:
            raise HubError("room_full", "room is full")
        room.participants[user_id] = Participant(user_id, name)
        return room

    def get_room(self, room_id: int) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise HubError("not_found", "room not found")
        return room

    # ---------- состояние ----------
    def _keys(self, room: Room) -> dict:
        """Ключ подсчёта: в дуэли — каждый участник, в команде — одна общая запись."""
        if room.mode == "team":
            return {"team": list(room.attempts)}
        return {
            uid: [a for a in room.attempts if a.user_id == uid]
            for uid in room.participants
        }

    def standings(self, room: Room) -> dict:
        start = room.started_at or now()
        return {
            k: compute_standing(v, room.task_ids, start)
            for k, v in self._keys(room).items()
        }

    def _standing_for(self, room: Room, st: dict, user_id: int) -> Standing:
        return st["team"] if room.mode == "team" else st[user_id]

    def snapshot(self, room: Room) -> dict:
        st = self.standings(room)
        return {
            "room_id": room.id,
            "mode": room.mode,
            "status": room.status,
            "started_at": iso(room.started_at),
            "ends_at": iso(room.ends_at),
            "tasks": room.task_ids,
            "participants": [
                {
                    "user_id": p.user_id, "name": p.name, "ready": p.ready,
                    "online": p.online, "left": p.left,
                    **self._standing_for(room, st, p.user_id).to_dict(),
                }
                for p in room.participants.values()
            ],
        }

    # ---------- рассылка ----------
    async def _send(self, room: Room, uid: int, msg: dict) -> None:
        ws = room.sockets.get(uid)
        if ws is None:
            return
        try:
            await ws.send_json(msg)
        except Exception:
            # Сокет умер; дисконнект обработает роутер.
            pass

    async def broadcast(self, room: Room, type_: str, data: dict,
                        exclude: Optional[int] = None) -> None:
        msg = {"type": type_, "data": data}
        for uid in list(room.sockets):
            if uid != exclude:
                await self._send(room, uid, msg)

    # ---------- WebSocket-уровень ----------
    async def connect(self, room_id: int, user_id: int, ws: WS) -> Room:
        room = self.get_room(room_id)
        p = room.participants.get(user_id)
        if p is None:
            raise HubError("forbidden", "not a participant of this room")
        was_known_offline = (not p.online) and (p.left or user_id in room.grace_tasks)
        task = room.grace_tasks.pop(user_id, None)
        if task:
            task.cancel()
        p.online, p.left = True, False
        room.sockets[user_id] = ws
        await self._send(room, user_id, {"type": "room_state", "data": self.snapshot(room)})
        if was_known_offline:
            await self.broadcast(room, "participant_reconnected", {"user_id": user_id}, exclude=user_id)
        else:
            await self.broadcast(room, "participant_joined",
                                 {"user_id": user_id, "name": p.name}, exclude=user_id)
        return room

    async def disconnect(self, room_id: int, user_id: int, ws: WS) -> None:
        room = self.rooms.get(room_id)
        if room is None or room.sockets.get(user_id) is not ws:
            return  # уже вытеснен новым соединением
        room.sockets.pop(user_id, None)
        p = room.participants[user_id]
        p.online = False
        if room.status == "finished":
            return
        await self.broadcast(room, "participant_disconnected",
                             {"user_id": user_id, "grace_seconds": self.grace_seconds})
        room.grace_tasks[user_id] = asyncio.create_task(self._grace(room, user_id))

    async def _grace(self, room: Room, user_id: int) -> None:
        try:
            await asyncio.sleep(self.grace_seconds)
        except asyncio.CancelledError:
            return
        room.grace_tasks.pop(user_id, None)
        p = room.participants[user_id]
        if not p.online:
            p.left = True
            await self.broadcast(room, "participant_left", {"user_id": user_id})

    async def handle_message(self, room_id: int, user_id: int, msg: dict) -> None:
        room = self.get_room(room_id)
        t = msg.get("type")
        if t == "ping":
            await self._send(room, user_id, {"type": "pong", "data": {}})
        elif t == "ready":
            if room.status != "waiting":
                return
            room.participants[user_id].ready = True
            await self.broadcast(room, "participant_ready", {"user_id": user_id})
            if (len(room.participants) == MAX_PARTICIPANTS
                    and all(p.ready for p in room.participants.values())):
                await self._start(room)
        else:
            await self._send(room, user_id, {"type": "error", "data": {
                "code": "unknown_type", "message": f"unknown message type: {t}"}})

    # ---------- жизненный цикл ----------
    async def _start(self, room: Room) -> None:
        room.status = "running"
        room.started_at = now()
        room.ends_at = room.started_at + timedelta(minutes=room.duration_minutes)
        await self.broadcast(room, "contest_started",
                             {"started_at": iso(room.started_at), "ends_at": iso(room.ends_at)})
        room.timer_task = asyncio.create_task(self._timer(room))

    async def _timer(self, room: Room) -> None:
        try:
            delay = (room.ends_at - now()).total_seconds()
            await asyncio.sleep(max(0, delay))
        except asyncio.CancelledError:
            return
        await self.finish(room, "time_over")

    async def finish(self, room: Room, reason: str) -> None:
        if room.status == "finished":
            return
        room.status = "finished"
        room.finished_at = now()
        room.finish_reason = reason
        if room.timer_task and room.timer_task is not asyncio.current_task():
            room.timer_task.cancel()
        for t in room.grace_tasks.values():
            t.cancel()
        st = self.standings(room)
        room.winner = decide_winner(st)
        await self.broadcast(room, "contest_finished", self.result(room))

    def result(self, room: Room) -> dict:
        st = self.standings(room)
        key = "winner_team_id" if room.mode == "team" else "winner_user_id"
        return {
            key: room.winner,
            "reason": room.finish_reason,
            "scores": {str(k): v.to_dict() for k, v in st.items()},
        }

    # ---------- вызывается Бэкендером 1 ----------
    async def publish_submission_result(
        self, room_id: Optional[int], submission_id: int, user_id: int,
        task_id: int, verdict: str, time_ms: Optional[int] = None,
    ) -> None:
        if room_id is None:
            return
        room = self.rooms.get(room_id)
        if room is None or room.status != "running":
            return
        at = now()
        if room.ends_at and at > room.ends_at:
            return
        if user_id not in room.participants or task_id not in room.task_ids:
            return
        room.attempts.append(Attempt(user_id, task_id, verdict, at))
        await self.broadcast(room, "submission_result", {
            "user_id": user_id, "task_id": task_id, "verdict": verdict,
            "time_ms": time_ms, "at": iso(at)})
        st = self.standings(room)
        for k, s in st.items():
            await self.broadcast(room, "progress_update", {
                "user_id": None if k == "team" else k,
                "team": k == "team",
                "solved": s.solved, "total": s.total,
                "penalty_seconds": s.penalty_seconds})
        if all(s.solved == s.total for s in st.values()):
            await self.finish(room, "all_solved")


hub = Hub()


async def publish_submission_result(**kwargs) -> None:
    """Точка входа для Бэкендера 1 (сигнатура из контракта)."""
    await hub.publish_submission_result(**kwargs)
