from __future__ import annotations

from sqlalchemy import func, select

from .models import AICall


def record_call(session, *, job_id, stage, provider, is_local, level, model, purpose) -> AICall:
    row = AICall(
        job_id=job_id, stage=stage, provider=provider, is_local=is_local,
        level=level, model=model, purpose=purpose,
    )
    session.add(row)
    session.flush()
    return row


def summary(session, job_id: int | None = None) -> dict:
    """The numbers the UI's audit panel shows. Both must be 0."""
    hosted = AICall.is_local.is_(False)
    q = select(
        func.count().label("total"),
        func.count().filter(AICall.level >= 3).label("level3_calls"),
        func.count().filter(hosted, AICall.level >= 2).label("hosted_calls_l2plus"),
        func.count().filter(hosted).label("hosted_calls_any"),
    ).select_from(AICall)
    if job_id is not None:
        q = q.where(AICall.job_id == job_id)
    return {k: int(v) for k, v in session.execute(q).one()._mapping.items()}
