"""The stage runner. Knows the order, the gates, and what a raised level undoes.

Gates (PRD A9, A6, §4 stage 7):
  - stages that use AI (2, 3, 4, 5, 8, 9) refuse to run while any Level 2 file
    is waiting for a community reviewer to confirm its level;
  - stages 7 and 8 refuse until attendance is entered and the analyst has
    counted the people behind every signed-off theme;
  - stage 8 refuses while an identifiability flag has no analyst decision.
Stage 4 has its own stop: it won't sort Level 2 material until a person has
checked the made-up names.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .models import IdentifyFlag, Job, Report, Segment, SourceFile, Theme, ThemeQuote, Unit
from .stages import (s0_intake, s1_ingest, s2_transcribe, s2b_diarise, s3_artefacts, s4_themes,
                     s5_evidence, s6_signoff, s7_identify, s8_report, s9_reportback)

STAGE_NAMES = {
    1: "Data Ingest", 2: "Audio Processing", 3: "Image Processing", 4: "Draft themes",
    5: "Evidence check", 6: "Community sign-off", 7: "Security Check", 8: "Reporting", 9: "Report back",
}
AI_STAGES = {2, 3, 4, 5, 8, 9}


class GateError(PermissionError):
    pass


def _stage2(session, job_id, **opts):
    if opts.get("only_diarise"):
        return {"diarisation": s2b_diarise.run(session, job_id, files=opts.get("files"))}
    out = s2_transcribe.run(session, job_id, **{k: v for k, v in opts.items() if k in ("variants", "files")})
    if opts.get("diarise", True):
        out["diarisation"] = s2b_diarise.run(session, job_id, files=opts.get("files"))
    return out


def _stage1(session, job_id, **opts):
    """Data Ingest: check every file has consent and a level, then convert them.
    PRD §4's stages 0 (Intake) and 1 (Ingest) in one — Ingest had nothing for a person to do."""
    out = s0_intake.run(session, job_id)
    out["ingested"] = s1_ingest.run(session, job_id)
    return out


# Stages 2–9 keep PRD §4's numbers. There is no stage 0: Intake is part of stage 1.
STAGES: dict[int, Callable] = {
    1: _stage1,
    2: _stage2,
    3: lambda s, j, **o: s3_artefacts.run(s, j, files=o.get("files")),
    4: lambda s, j, **o: s4_themes.run(s, j),
    5: lambda s, j, **o: s5_evidence.run(s, j),
    6: lambda s, j, **o: s6_signoff.run(s, j),
    7: lambda s, j, **o: {"flags": [f.id for f in s7_identify.run(s, j)]},
    8: lambda s, j, **o: {"report_id": s8_report.run(s, j).id},
    9: lambda s, j, **o: {"report_id": s9_reportback.run(s, j).id},
}


def _check_gates(session, job_id: int, n: int) -> None:
    if n in AI_STAGES:
        waiting = [f.filename for f in session.query(SourceFile).filter_by(job_id=job_id).all()
                   if f.level == 2 and not f.level_confirmed_by_community]
        if waiting:
            raise GateError("Level 2 material is waiting for a community reviewer to confirm its level "
                            f"(PRD A9): {waiting}")
    if n in (7, 8):
        if not s0_intake.attendance_total(session.get(Job, job_id)):
            raise GateError("enter how many people came to each session first (stage 1) — it's the 'of M' "
                            "in the report")
        missing = s7_identify.uncounted(session, job_id)
        if missing:
            raise GateError(f"the analyst hasn't counted the people behind these themes yet: {missing}")
    if n == 8 and s7_identify.open_flags(session, job_id):
        raise GateError("identifiability flags are still open — the analyst must decide and write down why")


def run_stage(session, job_id: int, n: int, **opts) -> dict:
    if n not in STAGES:
        raise ValueError(f"no stage {n}")
    if session.get(Job, job_id) is None:
        raise KeyError(job_id)
    _check_gates(session, job_id, n)
    t0 = time.time()
    result = STAGES[n](session, job_id, **opts) or {}
    result = dict(result) if isinstance(result, dict) else {"items": list(result)}
    result["stage"] = n
    result["seconds"] = round(time.time() - t0, 1)
    session.flush()
    return result


def raise_level(session, file_id: int, new_level: int) -> SourceFile:
    """The community can raise a level any time. Raising to 3 pulls the file's
    material out of everything AI has already produced."""
    sf = s0_intake.set_level(session, file_id, new_level, actor_role="community")
    if new_level >= 3:
        units = session.query(Unit).filter_by(file_id=file_id).all()
        touched: set[int] = set()
        for u in units:
            u.excluded = True
            for tq in session.query(ThemeQuote).filter_by(unit_id=u.id).all():
                touched.add(tq.theme_id)
                session.delete(tq)
        session.query(Segment).filter_by(file_id=file_id).delete(synchronize_session=False)
        session.flush()
        for tid in touched:
            t = session.get(Theme, tid)
            if t.agreed_upfront:
                continue  # the community's own theme stays; it just lost those quotes
            if not s5_evidence.check_structural(session, tid):
                t.status = "unsupported"
                t.review_note = (t.review_note + "\n" if t.review_note else "") + \
                    f"evidence: material from '{sf.filename}' was raised to Level 3 and withdrawn"
        session.flush()
    return sf


def reset_job(session, job_id: int, exports_dir: Path | None = None) -> dict:
    """Take a job back to intake: everything the stages made is removed, the raw input stays.

    Kept: the uploaded files with their consent records, levels and community
    confirmations; concerns people raised; and the ai_calls log, which is the
    evidence for the §5 zero and is never rewritten. Ingest's converted copies
    live in a cache shared by file hash, so they are left to be overwritten when
    stage 1 runs again. Pictures ingest pulled out of slides are removed — stage 1
    pulls them out again.
    """
    from .models import Artefact, Pseudonym, Review
    from .stages.s1_ingest import brief_from_xlsx

    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    theme_ids = [t.id for t in session.query(Theme).filter_by(job_id=job_id)]
    if theme_ids:
        for model in (IdentifyFlag, Review, ThemeQuote):
            session.query(model).filter(model.theme_id.in_(theme_ids)).delete(synchronize_session=False)
    session.query(Theme).filter_by(job_id=job_id).delete(synchronize_session=False)
    session.query(Unit).filter_by(job_id=job_id).delete(synchronize_session=False)
    session.query(Report).filter_by(job_id=job_id).delete(synchronize_session=False)
    session.query(Pseudonym).filter_by(job_id=job_id).delete(synchronize_session=False)
    files = session.query(SourceFile).filter_by(job_id=job_id).all()
    file_ids = [f.id for f in files]
    if file_ids:
        session.query(Segment).filter(Segment.file_id.in_(file_ids)).delete(synchronize_session=False)
        session.query(Artefact).filter(Artefact.file_id.in_(file_ids)).delete(synchronize_session=False)
    removed_children = 0
    for f in files:
        if (f.provenance or {}).get("embedded_in"):  # a picture ingest pulled out of a slide deck
            session.delete(f)
            removed_children += 1
            continue
        if f.kind == "brief" and (f.provenance or {}).get("ingested_path") and job.brief:
            try:  # take out only the text ingest added, not a brief someone typed
                job.brief = job.brief.replace(brief_from_xlsx(Path(f.path)), "").strip()
            except Exception:  # noqa: BLE001 — the raw file moved; leave the brief as it is
                pass
        f.provenance = {}
        f.names_checked = False
    job.attendance = []
    job.status = "intake"
    session.flush()
    removed_exports = 0
    if exports_dir is not None and Path(exports_dir).exists():
        for p in Path(exports_dir).glob(f"job{job_id}_*"):
            p.unlink()
            removed_exports += 1
    return {"job_id": job_id, "themes_removed": len(theme_ids), "slide_pictures_removed": removed_children,
            "exports_removed": removed_exports}


def status(session, job_id: int) -> dict:
    job = session.get(Job, job_id)
    files = session.query(SourceFile).filter_by(job_id=job_id).all()
    ingested = [f for f in files if f.provenance and f.provenance.get("ingested_path")]
    segs = session.query(Segment).join(SourceFile).filter(SourceFile.job_id == job_id).count()
    n_units = session.query(Unit).filter_by(job_id=job_id).count()
    themes = session.query(Theme).filter_by(job_id=job_id).all()
    flags = (session.query(IdentifyFlag).join(Theme, Theme.id == IdentifyFlag.theme_id)
             .filter(Theme.job_id == job_id).all())
    reports = {r.kind: r for r in session.query(Report).filter_by(job_id=job_id).all()}
    from .stages.s3_artefacts import Artefact

    arts = session.query(Artefact).join(SourceFile).filter(SourceFile.job_id == job_id).count()
    waiting_l2 = [f.filename for f in files if f.level == 2 and not f.level_confirmed_by_community]
    quoted = session.query(ThemeQuote).join(Theme).filter(Theme.job_id == job_id).count()
    drafts = any(t.status == "draft" for t in themes)
    stages = [
        {"n": 1, "done": bool(files) and all(f.consent_id for f in files) and len(ingested) == len(files)},
        {"n": 2, "done": segs > 0},
        {"n": 3, "done": arts > 0},
        {"n": 4, "done": bool(quoted or drafts) and job.status != "stage4:waiting-names"},
        {"n": 5, "done": job.status.startswith("stage5") or any(t.status != "draft" for t in themes)},
        {"n": 6, "done": bool(themes) and all(t.decided_by for t in themes if t.status not in ("unsupported",))},
        {"n": 7, "done": bool(themes) and all(f.decision for f in flags)
                 and (bool(flags) or job.status.startswith(("stage7", "stage8", "stage9", "done")))},
        {"n": 8, "done": "client" in reports and bool(reports["client"].markdown)},
        {"n": 9, "done": "reportback" in reports and reports["reportback"].sent},
    ]
    # What each stage is waiting on a person for, in a few words; "" when nothing.
    waiting_names = s4_themes.waiting_name_check(session, job_id)
    uncounted = s7_identify.uncounted(session, job_id)
    open_flags = [f for f in flags if f.decision is None]
    client, back = reports.get("client"), reports.get("reportback")
    waiting = {
        1: ("community to confirm levels" if waiting_l2 else
            "who came" if files and not s0_intake.attendance_total(job) else ""),
        4: "name check" if waiting_names else "",
        6: "community sign-off" if any(t.decided_by is None for t in themes if t.status != "unsupported") else "",
        7: ("people counts" if uncounted else "analyst decisions" if open_flags else ""),
        8: ("approvals" if client and client.markdown and not (client.approved_community and client.approved_analyst)
            else ""),
        9: "analyst approval" if back and not back.sent else "",
    }
    for s in stages:
        s["name"] = STAGE_NAMES[s["n"]]
        s["waiting"] = waiting.get(s["n"], "")
    return {
        "job_id": job_id, "name": job.name, "status": job.status, "stages": stages,
        "files": len(files), "segments": segs, "units": n_units, "themes": len(themes),
        "open_flags": len(open_flags),
        "waiting_level2": waiting_l2,
        "waiting_names": waiting_names,
        "attendance_total": s0_intake.attendance_total(job),
        "uncounted": uncounted,
    }
