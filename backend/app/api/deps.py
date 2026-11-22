from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db

DB = Annotated[Session, Depends(get_db)]


class Pagination:
    def __init__(self, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset


Paging = Annotated[Pagination, Depends()]


def paginate(db: Session, stmt, paging: Pagination):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = list(db.scalars(stmt.limit(paging.limit).offset(paging.offset)))
    return items, total or 0


def get_or_404(db: Session, model, obj_id: int, name: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{name} {obj_id} not found")
    return obj
