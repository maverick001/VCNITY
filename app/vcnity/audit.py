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
    q = select(AICall)
    if job_id is not None:
        q = q.where(AICall.job_id == job_id)
    rows = session.execute(q).scalars().all()
    return {
        "total": len(rows),
        "level3_calls": sum(1 for r in rows if r.level >= 3),
        "hosted_calls_l2plus": sum(1 for r in rows if (not r.is_local) and r.level >= 2),
        "hosted_calls_any": sum(1 for r in rows if not r.is_local),
    }
