"""
GroupService — lógica para grupos privados de participantes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from app.exceptions import AlreadyMemberError, GroupNotFoundError
from app.models import PoolGroup, TournamentPhase, User, UserPoolGroup, _random_code
from app.modules.leaderboard.service import LeaderboardEntry, LeaderboardService

logger = logging.getLogger("polla.groups")


@dataclass
class GroupInfo:
    group: PoolGroup
    member_count: int
    is_creator: bool


class GroupService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_group(
        self,
        user_id: int,
        name: str,
        start_phase: TournamentPhase | None = None,
    ) -> PoolGroup:
        code = _random_code()
        while self._session.exec(select(PoolGroup).where(PoolGroup.join_code == code)).first():
            code = _random_code()

        group = PoolGroup(
            name=name.strip(),
            join_code=code,
            creator_id=user_id,
            start_phase=start_phase,
        )
        self._session.add(group)
        self._session.flush()

        membership = UserPoolGroup(user_id=user_id, group_id=group.id)
        self._session.add(membership)
        self._session.commit()
        self._session.refresh(group)
        logger.info("Grupo '%s' creado por user_id=%d (código=%s)", name, user_id, code)
        return group

    def join_group(self, user_id: int, join_code: str) -> PoolGroup:
        code = join_code.upper().strip()
        group = self._session.exec(
            select(PoolGroup).where(PoolGroup.join_code == code)
        ).first()
        if group is None:
            raise GroupNotFoundError(f"No existe un grupo con el código «{join_code}»")

        existing = self._session.exec(
            select(UserPoolGroup).where(
                UserPoolGroup.user_id == user_id,
                UserPoolGroup.group_id == group.id,
            )
        ).first()
        if existing:
            raise AlreadyMemberError("Ya eres miembro de este grupo")

        membership = UserPoolGroup(user_id=user_id, group_id=group.id)
        self._session.add(membership)
        self._session.commit()
        logger.info("user_id=%d se unió al grupo '%s' (id=%d)", user_id, group.name, group.id)
        return group

    def get_user_groups(self, user_id: int) -> list[GroupInfo]:
        memberships = self._session.exec(
            select(UserPoolGroup).where(UserPoolGroup.user_id == user_id)
        ).all()

        result = []
        for m in memberships:
            group = self._session.get(PoolGroup, m.group_id)
            if group is None:
                continue
            member_count = len(
                self._session.exec(
                    select(UserPoolGroup).where(UserPoolGroup.group_id == group.id)
                ).all()
            )
            result.append(
                GroupInfo(
                    group=group,
                    member_count=member_count,
                    is_creator=group.creator_id == user_id,
                )
            )
        return result

    def get_group(self, group_id: int) -> PoolGroup | None:
        return self._session.get(PoolGroup, group_id)

    def is_member(self, user_id: int, group_id: int) -> bool:
        return bool(
            self._session.exec(
                select(UserPoolGroup).where(
                    UserPoolGroup.user_id == user_id,
                    UserPoolGroup.group_id == group_id,
                )
            ).first()
        )

    def set_start_phase(
        self,
        group_id: int,
        user_id: int,
        start_phase: TournamentPhase | None,
    ) -> bool:
        group = self.get_group(group_id)
        if group is None or group.creator_id != user_id:
            return False
        group.start_phase = start_phase
        self._session.add(group)
        self._session.commit()
        self._session.refresh(group)
        logger.info(
            "Grupo %d: start_phase cambiada a %s por user_id=%d",
            group_id, start_phase, user_id,
        )
        return True

    def get_group_leaderboard(self, group_id: int) -> list[LeaderboardEntry]:
        group = self.get_group(group_id)
        memberships = self._session.exec(
            select(UserPoolGroup).where(UserPoolGroup.group_id == group_id)
        ).all()
        member_ids = {m.user_id for m in memberships}

        lb_svc = LeaderboardService(self._session)
        min_phase = group.start_phase if group else None
        filtered = lb_svc.get_leaderboard_filtered(user_ids=member_ids, min_phase=min_phase)

        for i, entry in enumerate(filtered, start=1):
            entry.position = i
        return filtered
