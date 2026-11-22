from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, Paging, get_or_404, paginate
from app.models import Connector, QualityReport
from app.schemas import Page, QualityReportOut

router = APIRouter(tags=["quality"])


def _out(r: QualityReport, names: dict[int, str]) -> QualityReportOut:
    o = QualityReportOut.model_validate(r)
    o.connector_name = names.get(r.connector_id)
    return o


@router.get("/quality-reports", response_model=Page[QualityReportOut])
def list_reports(db: DB, paging: Paging, connector_id: int | None = None, overall_status: str | None = None):
    stmt = select(QualityReport).order_by(QualityReport.created_at.desc())
    if connector_id:
        stmt = stmt.where(QualityReport.connector_id == connector_id)
    if overall_status:
        stmt = stmt.where(QualityReport.overall_status == overall_status)
    items, total = paginate(db, stmt, paging)
    names = {c.id: c.connector_name for c in db.scalars(select(Connector))}
    return Page(items=[_out(r, names) for r in items], total=total, limit=paging.limit, offset=paging.offset)


@router.get("/quality-reports/{report_id}", response_model=QualityReportOut)
def get_report(report_id: int, db: DB):
    r = get_or_404(db, QualityReport, report_id, "Quality report")
    return _out(r, {c.id: c.connector_name for c in db.scalars(select(Connector))})
