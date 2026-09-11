"""The stage runner. Knows the order, the gates, and what a raised level undoes.

Gates (PRD A4, §4 stage 7):
  - stages that use AI (2, 3, 4, 5, 8, 9) refuse to run while any Level 2 file
    is waiting for a community reviewer to confirm its level;
  - stage 8 refuses while an identifiability flag has no analyst decision.
"""
from __future__ import annotations

import time
from typing import Callable

from .models import IdentifyFlag, Job, Report, Segment, SourceFile, Theme, ThemeQuote, Unit
from .stages import (s0_intake, s1_ingest, s2_transcribe, s2b_diarise, s3_artefacts, s4_themes,
                     s5_evidence, s6_signoff, s7_identify, s8_report, s9_reportback)

STAGE_NAMES = {
    0: "Intake", 1: "Ingest", 2: "Transcription", 3: "Things people made", 4: "Draft themes",
    5: "Evidence check", 6: "Community sign-off", 7: "Could anyone be identified?", 8: "Report", 9: "Report back",
}
AI_STAGES = {2, 3, 4, 5, 8, 9}


class GateError(PermissionError):
    pass


def _stage2(session, job_id, **opts):
    out = s2_transcribe.run(session, job_id, **{k: v for k, v in opts.items() if k in ("variants", "files")})
    if opts.get("diarise", True):
        out["diarisation"] = s2b_diarise.run(session, job_id, files=opts.get("files"))
    return out


STAGES: dict[int, Callable] = {
    0: lambda s, j, **o: s0_intake.run(s, j),
    1: lambda s, j, **o: s1_ingest.run(s, j),
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
                            f"(PRD A4): {waiting}")
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
            if not s5_evidence.check_structural(session, tid):
                t = session.get(Theme, tid)
                t.status = "unsupported"
                t.review_note = (t.review_note + "\n" if t.review_note else "") + \
                    f"evidence: material from '{sf.filename}' was raised to Level 3 and withdrawn"
        session.flush()
    return sf


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
    stages = [
        {"n": 0, "done": bool(files) and all(f.consent_id for f in files)},
        {"n": 1, "done": bool(files) and len(ingested) == len([f for f in files if f.kind != "brief"]) + 0},
        {"n": 2, "done": segs > 0},
        {"n": 3, "done": arts > 0},
        {"n": 4, "done": bool(themes)},
        {"n": 5, "done": job.status.startswith("stage5") or any(t.status != "draft" for t in themes)},
        {"n": 6, "done": bool(themes) and all(t.decided_by for t in themes if t.status not in ("unsupported",))},
        {"n": 7, "done": bool(themes) and job.status.startswith(("stage7", "stage8", "stage9", "done"))
                 and all(f.decision for f in flags)},
        {"n": 8, "done": "client" in reports and bool(reports["client"].markdown)},
        {"n": 9, "done": "reportback" in reports and reports["reportback"].sent},
    ]
    for s in stages:
        s["name"] = STAGE_NAMES[s["n"]]
    return {
        "job_id": job_id, "name": job.name, "status": job.status, "stages": stages,
        "files": len(files), "segments": segs, "units": n_units, "themes": len(themes),
        "open_flags": sum(1 for f in flags if f.decision is None),
        "waiting_level2": waiting_l2,
    }
