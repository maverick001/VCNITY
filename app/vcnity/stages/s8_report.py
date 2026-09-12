"""Stage 8 — Report. Drafts recommendations against the brief. Analyst edits.
Community and analyst both approve before it leaves.

Shape follows the client's own examples (Shape Your Ipswich): Background → How
we engaged → What the community told us (a Theme | N of M (X%) table) →
Findings → Sources. Only signed-off themes appear: confirmed, fixed, added —
never rejected, cut, draft or unsupported. The findings narrative is drafted
from the table alone, so it cannot say more than the community signed off on.
"""
from __future__ import annotations

from pathlib import Path

from ..export import report_to_docx
from ..models import Job, Report, SourceFile, Theme, Unit
from ..providers import router

INCLUDED = ("confirmed", "fixed", "added")

SYSTEM = (
    "You write the Findings section of a community engagement report for a local government reader. "
    "Formal, third person, short paragraphs. You may only use what is in the theme table. "
    "No new facts, no causes the table does not state, no recommendations beyond what the themes say."
)
PROMPT = (
    "BRIEF:\n{brief}\n\nTHEME TABLE (theme — how many of the participants — summary):\n{table}\n\n"
    "Write a Findings section of three to five short paragraphs that answers the brief using only the table. "
    "Use hedged quantifiers that match the numbers (most / several / a few / one). "
    "End with one paragraph headed 'Overall interpretation'. Plain text, no markdown headings."
)


def included_themes(session, job_id: int) -> list[Theme]:
    return (session.query(Theme).filter(Theme.job_id == job_id, Theme.status.in_(INCLUDED))
            .order_by(Theme.n_people.desc(), Theme.id).all())


def participants(session, job_id: int) -> int:
    keys = {k for (k,) in session.query(Unit.speaker_key)
            .filter(Unit.job_id == job_id, Unit.excluded.is_(False)).distinct().all()}
    return max(len(keys), 1)


def theme_table(session, job_id: int) -> list[dict]:
    m = participants(session, job_id)
    rows = []
    for t in included_themes(session, job_id):
        people = {tq.unit.speaker_key for tq in t.quotes if not tq.unit.excluded}
        n = len(people)
        rows.append({"id": t.id, "label": t.label, "n": n, "m": m, "pct": round(100 * n / m), "summary": t.summary,
                     "status": t.status, "quote_ids": [tq.unit_id for tq in t.quotes if not tq.unit.excluded]})
    return rows


def how_we_engaged(session, job_id: int) -> list[dict]:
    out = []
    for f in session.query(SourceFile).filter_by(job_id=job_id).order_by(SourceFile.id).all():
        if f.kind == "brief":
            continue
        d = {"filename": f.filename, "kind": f.kind, "level": f.level}
        if f.provenance.get("duration_s"):
            d["detail"] = f"{round(f.provenance['duration_s'] / 60)} min recording"
        elif f.kind == "image":
            d["detail"] = "photo of something a participant made"
        elif f.kind == "text":
            d["detail"] = f"{f.provenance.get('chars', 0)} characters of text"
        out.append(d)
    return out


def _table_md(table: list[dict]) -> str:
    lines = ["| Theme | Who said it | Summary |", "| --- | --- | --- |"]
    for r in table:
        lines.append(f"| {r['label']} | {r['n']} of {r['m']} participants ({r['pct']}%) | {r['summary']} |")
    return "\n".join(lines)


def render_markdown(job: Job, table: list[dict], engaged: list[dict], findings: str) -> str:
    parts = [f"# {job.name}", "", "## Background", "", job.brief or "_No brief supplied._", "",
             "## How we engaged", ""]
    if engaged:
        for e in engaged:
            parts.append(f"- {e['filename']} — {e.get('detail', e['kind'])} (Level {e['level']})")
    else:
        parts.append("_No material recorded._")
    parts += ["", "## What the community told us", "",
              _table_md(table) if table else "_No themes have been signed off yet._", "",
              "## Findings", "", findings.strip() or "_Not drafted yet._", "", "## Sources", ""]
    for r in table:
        parts.append(f"- **{r['label']}** — quotes {', '.join('#' + str(q) for q in r['quote_ids'])}")
    parts.append("")
    parts.append("_Every theme above was confirmed by community reviewers before this report was drafted. "
                 "Quote numbers point at the job's evidence record; raw material never leaves the pipeline._")
    return "\n".join(parts)


def run(session, job_id: int) -> Report:
    job = session.get(Job, job_id)
    table = theme_table(session, job_id)
    engaged = how_we_engaged(session, job_id)
    findings = ""
    if table:
        level = max(session.get(Theme, r["id"]).level for r in table)
        findings = router.call(
            session, job_id=job_id, stage=8, level=level, purpose="report-findings",
            prompt=PROMPT.format(brief=job.brief or "(none)",
                                 table="\n".join(f"- {r['label']} — {r['n']} of {r['m']} ({r['pct']}%) — {r['summary']}"
                                                 for r in table)),
            system=SYSTEM, redacted=True,
        )
    md = render_markdown(job, table, engaged, findings)
    rep = session.query(Report).filter_by(job_id=job_id, kind="client").one_or_none()
    if rep is None:
        rep = Report(job_id=job_id, kind="client")
        session.add(rep)
    rep.markdown = md
    rep.approved_community = False  # any redraft needs approving again
    rep.approved_analyst = False
    job.status = "stage8:drafted"
    session.flush()
    return rep


def edit(session, report_id: int, markdown: str) -> Report:
    """The analyst edits. Approvals reset — what was approved is no longer what is written."""
    rep = session.get(Report, report_id)
    rep.markdown = markdown
    rep.approved_community = rep.approved_analyst = False
    session.flush()
    return rep


def approve(session, report_id: int, actor_role: str) -> Report:
    rep = session.get(Report, report_id)
    if rep is None:
        raise KeyError(report_id)
    if actor_role == "community":
        rep.approved_community = True
    elif actor_role == "analyst":
        rep.approved_analyst = True
    else:
        raise ValueError("only community or analyst can approve")
    session.flush()
    return rep


def export(session, report_id: int, out_dir: Path) -> tuple[Path, Path]:
    rep = session.get(Report, report_id)
    if not (rep.approved_community and rep.approved_analyst):
        raise PermissionError("both the community and the analyst must approve before a report leaves")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"job{rep.job_id}_{rep.kind}"
    md_path = out_dir / f"{stem}.md"
    md_path.write_text(rep.markdown, encoding="utf-8")
    docx_path = report_to_docx(rep.markdown, out_dir / f"{stem}.docx")
    return md_path, docx_path
