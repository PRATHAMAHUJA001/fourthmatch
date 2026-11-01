"""SQLAlchemy rule repository. Implements the domain RuleRepository shape."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.infra.db.models.decision import Rule


class SqlRuleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_rule(self, **fields: Any) -> Rule:
        row = Rule(**fields)
        self._session.add(row)
        self._session.flush()
        return row

    def get_rule(self, rule_pk: int) -> Rule | None:
        return self._session.get(Rule, rule_pk)

    def list_rules(self, status: str | None = None) -> list[Rule]:
        query = self._session.query(Rule)
        if status is not None:
            query = query.filter(Rule.status == status)
        return query.order_by(Rule.id).all()

    def set_status(self, rule_pk: int, status: str) -> Rule | None:
        row = self._session.get(Rule, rule_pk)
        if row is None:
            return None
        row.status = status
        self._session.flush()
        return row

    def set_conflicts(self, rule_pk: int, conflict_with: list[str]) -> Rule | None:
        row = self._session.get(Rule, rule_pk)
        if row is None:
            return None
        row.conflict_with = list(conflict_with)
        self._session.flush()
        return row

    def commit(self) -> None:
        self._session.commit()
