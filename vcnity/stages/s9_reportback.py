"""Stage 9 — Report back. A plain-language version for participants: what came
of what they said, told plainly. Same dual approval as the client report;
"send" only marks it sent — nothing is transmitted by the prototype.
"""
from __future__ import annotations

from ..models import Job, Report, Theme
from ..providers import router
from .s8_report import INCLUDED, theme_table

SYSTEM = (
    "You rewrite a community engagement report for the people who took part. "
    "Second person ('you told us'). Short sentences. No jargon, no percentages, no headings in capitals. "
    "You may only restate what the report says. Nothing new."
)
PROMPT = (
    "Here is the report that will go to the client:\n\n{report}\n\n"
    "Write the version that goes back to the participants. Start with what they told us, theme by theme, "
    "in plain words. Then say plainly what will happen next with it, using only what the report says. "
    "Keep it under 300 words."
)


def run(session, job_id: int) -> Report:
    job = session.get(Job, job_id)
    client = session.query(Report).filter_by(job_id=job_id, kind="client").one_or_none()
    if client is None or not client.markdown.strip():
        raise ValueError("draft the client report (stage 8) first")
    table = theme_table(session, job_id)
    level = max((session.get(Theme, r["id"]).level for r in table), default=1)
    text = router.call(session, job_id=job_id, stage=9, level=level, purpose="report-back",
                       prompt=PROMPT.format(report=client.markdown), system=SYSTEM, redacted=True)
    rb = session.query(Report).filter_by(job_id=job_id, kind="reportback").one_or_none()
    if rb is None:
        rb = Report(job_id=job_id, kind="reportback")
        session.add(rb)
    rb.markdown = f"# What you told us — {job.name}\n\n{text.strip()}"
    rb.approved_community = rb.approved_analyst = False
    rb.sent = False
    job.status = "stage9:drafted"
    session.flush()
    return rb


def send(session, report_id: int) -> Report:
    rb = session.get(Report, report_id)
    if rb is None or rb.kind != "reportback":
        raise KeyError(report_id)
    if not (rb.approved_community and rb.approved_analyst):
        raise PermissionError("both the community and the analyst must approve before it goes back")
    rb.sent = True
    job = session.get(Job, rb.job_id)
    job.status = "done"
    session.flush()
    return rb
