"""Чистая логика подсчёта очков. Без зависимостей от FastAPI/БД — легко тестируется.

Правила (ICPC-подобные):
- решённая задача = первый вердикт OK по ней;
- штраф = время от старта до OK + PENALTY_PER_WRONG за каждую неудачную попытку ДО OK;
- CE не считается неудачной попыткой, попытки после OK игнорируются;
- победитель: больше решённых -> меньше штраф -> раньше последний OK -> иначе ничья.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Hashable, Iterable, Optional

PENALTY_PER_WRONG = 20 * 60  # секунд
COUNTED_WRONG = {"WA", "TLE", "RE"}


@dataclass(frozen=True)
class Attempt:
    user_id: int
    task_id: int
    verdict: str
    at: datetime


@dataclass
class TaskState:
    status: str = "none"  # none | wrong | solved
    by: Optional[int] = None  # кто решил (для командного режима)
    wrong_count: int = 0


@dataclass
class Standing:
    solved: int = 0
    total: int = 0
    penalty_seconds: int = 0
    last_ok_at: Optional[datetime] = None
    tasks: dict[int, TaskState] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "solved": self.solved,
            "total": self.total,
            "penalty_seconds": self.penalty_seconds,
            "tasks": {
                str(tid): {"status": t.status, "by": t.by}
                for tid, t in self.tasks.items()
            },
        }


def compute_standing(
    attempts: Iterable[Attempt], task_ids: list[int], started_at: datetime
) -> Standing:
    """Считает положение по набору попыток (одного участника или всей команды)."""
    st = Standing(total=len(task_ids), tasks={t: TaskState() for t in task_ids})
    for a in sorted(attempts, key=lambda x: x.at):
        ts = st.tasks.get(a.task_id)
        if ts is None or ts.status == "solved":
            continue
        if a.verdict == "OK":
            ts.status, ts.by = "solved", a.user_id
            elapsed = max(0, int((a.at - started_at).total_seconds()))
            st.solved += 1
            st.penalty_seconds += elapsed + ts.wrong_count * PENALTY_PER_WRONG
            st.last_ok_at = a.at
        elif a.verdict in COUNTED_WRONG:
            ts.status = "wrong"
            ts.wrong_count += 1
    return st


def decide_winner(standings: dict[Hashable, Standing]) -> Optional[Hashable]:
    """Возвращает ключ победителя или None при ничьей."""
    if not standings:
        return None

    def key(item):
        _, s = item
        last = s.last_ok_at.timestamp() if s.last_ok_at else float("inf")
        return (-s.solved, s.penalty_seconds, last)

    ranked = sorted(standings.items(), key=key)
    best, best_key = ranked[0][0], key(ranked[0])
    if best_key[0] == 0:  # никто ничего не решил
        return None
    if len(ranked) > 1 and key(ranked[1]) == best_key:
        return None
    return best
