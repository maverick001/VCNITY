"""Run the whole pipeline once on Data/raw so the demo walks the stages instantly.

    uv run --project app python app/scripts/precompute.py --confirm-levels
    uv run --project app python app/scripts/precompute.py --confirm-levels --demo-signoff
    uv run --project app python app/scripts/precompute.py --job 1 --stages 2 --only-diarise   # after HF_TOKEN arrives
    uv run --project app python app/scripts/precompute.py --job 1 --reset-signoff              # back to stage 6 for a live run

Stages 1–5 are the slow AI parts. Stages 6–9 need people; --demo-signoff fills
them in with clearly labelled demo decisions so the report pages have content.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vcnity import db, pipeline  # noqa: E402
from vcnity.config import settings  # noqa: E402
from vcnity.models import IdentifyFlag, Job, Report, Review, SourceFile, Theme  # noqa: E402
from vcnity.stages import s0_intake, s6_signoff, s7_identify, s8_report  # noqa: E402

JOB_NAME = "FQI co-design session — September 2026"
CONSENT = "session-consent-2026-09-03"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.cache_dir / "precompute.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def create_job(session, confirm: bool) -> int:
    existing = session.query(Job).filter_by(name=JOB_NAME).one_or_none()
    if existing:
        log(f"job already exists: id={existing.id}")
        return existing.id
    job = s0_intake.create_job(session, JOB_NAME)
    data = settings.data_dir
    if not data.exists():
        raise SystemExit(f"data dir not found: {data} (set VCNITY_DATA_DIR)")
    for p in sorted(data.iterdir()):
        suf = p.suffix.lower()
        if suf in (".m4a", ".wav", ".mp3"):
            level, scope = 2, "recording of a public co-design session; personal experience likely"
        elif suf in (".jpg", ".jpeg", ".png"):
            level, scope = 2, "photo of a participant-made artefact; personal experience on it"
        elif suf == ".xlsx":
            level, scope = 1, "client brief — not participant material"
        elif suf in (".docx", ".pptx", ".txt", ".md"):
            level, scope = 2, "text supplied with the session"
        else:
            log(f"skipping {p.name}")
            continue
        sf = s0_intake.add_file(session, job.id, p, level=level,
                                consent_label=CONSENT if level > 1 else "client", consent_scope=scope)
        if confirm and level == 2:
            s0_intake.confirm_level(session, sf.id)
        log(f"added {p.name} as {sf.kind} at Level {level}{' (confirmed)' if confirm and level == 2 else ''}")
    return job.id


def demo_signoff(session, job_id: int) -> None:
    """Stand-in decisions so stages 7–9 can run. Every one is labelled as demo."""
    for t in session.query(Theme).filter_by(job_id=job_id, status="draft").all():
        s6_signoff.review(session, t.id, actor_role="community", action="confirm",
                          note="DEMO: auto-confirmed for the walkthrough — redo this live")
    log("demo sign-off: confirmed every draft theme (labelled)")


def demo_decide_flags(session, job_id: int) -> None:
    for f in s7_identify.open_flags(session, job_id):
        s7_identify.decide(session, f.id, "keep", reason="DEMO: kept so the report has content — decide this live")
    log("demo flags: kept every open flag (labelled)")


def reset_signoff(session, job_id: int) -> None:
    for t in session.query(Theme).filter_by(job_id=job_id).all():
        if t.status in ("confirmed", "fixed", "cut", "rejected"):
            t.status = "draft"
            t.decided_by = None
            t.review_note = ""
    session.query(IdentifyFlag).filter(IdentifyFlag.theme_id.in_(
        [t.id for t in session.query(Theme).filter_by(job_id=job_id)])).delete(synchronize_session=False)
    session.query(Review).filter(Review.theme_id.in_(
        [t.id for t in session.query(Theme).filter_by(job_id=job_id)])).delete(synchronize_session=False)
    session.query(Report).filter_by(job_id=job_id).delete(synchronize_session=False)
    session.get(Job, job_id).status = "stage5:done"
    log("reset: themes back to draft, flags/reviews/reports cleared — ready for a live sign-off")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=int)
    ap.add_argument("--stages", default="1,2,3,4,5")
    ap.add_argument("--confirm-levels", action="store_true")
    ap.add_argument("--demo-signoff", action="store_true")
    ap.add_argument("--only-diarise", action="store_true")
    ap.add_argument("--reset-signoff", action="store_true")
    args = ap.parse_args()

    db.init_db()
    log(f"data dir {settings.data_dir} · text model {settings.ollama_model} · "
        f"vision model {settings.ollama_vision_model} · HF token {'yes' if settings.hf_token else 'no'}")

    with db.session() as s:
        job_id = args.job or create_job(s, args.confirm_levels)
        if args.confirm_levels and args.job:
            for f in s.query(SourceFile).filter_by(job_id=job_id, level=2).all():
                s0_intake.confirm_level(s, f.id)

    if args.reset_signoff:
        with db.session() as s:
            reset_signoff(s, job_id)
        return 0

    stages = [int(x) for x in args.stages.split(",") if x.strip()]
    for n in stages:
        opts = {"only_diarise": True} if (n == 2 and args.only_diarise) else {}
        log(f"stage {n} ({pipeline.STAGE_NAMES[n]}) …")
        t0 = time.time()
        try:
            with db.session() as s:
                out = pipeline.run_stage(s, job_id, n, **opts)
        except Exception as e:  # noqa: BLE001
            log(f"stage {n} FAILED after {time.time() - t0:.0f}s: {type(e).__name__}: {e}")
            return 1
        brief = {k: v for k, v in out.items() if k not in ("items", "diff")}
        log(f"stage {n} done in {time.time() - t0:.0f}s: {brief}")

    if args.demo_signoff:
        with db.session() as s:
            demo_signoff(s, job_id)
            pipeline.run_stage(s, job_id, 6)
        with db.session() as s:
            flags = pipeline.run_stage(s, job_id, 7)
            log(f"stage 7: {flags}")
            demo_decide_flags(s, job_id)
        for n in (8, 9):
            t0 = time.time()
            with db.session() as s:
                out = pipeline.run_stage(s, job_id, n)
            log(f"stage {n} done in {time.time() - t0:.0f}s: {out}")

    with db.session() as s:
        st = pipeline.status(s, job_id)
    log(f"status: {st}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
