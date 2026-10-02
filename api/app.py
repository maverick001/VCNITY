"""Flask API over the pipeline. Owns the database; runs stages in a background
thread. The Reflex UI talks only to this.

Every request but /health and /auth/login needs a signed-in account (see
PERMISSIONS below and vcnity/auth.py). Tests run with auth off unless they ask.

Rules become status codes:
    not signed in               → 401
    wrong role or other job     → 403
    lowering a level            → 400
    analyst overrides community → 409
    AI stage before confirmation→ 409
    export before both approve  → 403
"""
from __future__ import annotations

import mimetypes
import threading
import time
import traceback
from pathlib import Path

from flask import Flask, g, jsonify, request, send_file
from werkzeug.utils import secure_filename

from vcnity import ask, audit, auth, db, model_choice, pipeline
from vcnity.config import settings
from vcnity.models import (Artefact, Concern, IdentifyFlag, Job, Pseudonym, Report, Segment, SourceFile, Theme,
                           Unit)
from vcnity.stages import (concerns, s0_intake, s2_transcribe, s4_themes, s6_signoff, s7_identify, s8_report,
                           s9_reportback)
from vcnity.wordlist import load_wordlist, person_names, save_wordlist

RUNS: dict[int, dict] = {}  # job_id → {stage, started, finished, error, result}

# Who may call what, by endpoint (the view function's name). Anything not listed is refused.
# The community and the client are also held to their own job (see _job_of). PRD §3, A19–A21.
F, C, A, CL = "facilitator", "community", "analyst", "client"
STAFF, EVERYONE = (F, A), (F, C, A, CL)
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "me": EVERYONE, "list_jobs": EVERYONE, "get_job": EVERYONE, "reports": EVERYONE,
    "create_job": (F,), "set_attendance": (F,), "upload": (F,), "add_local": (F,),
    "add_agreed_theme": (C,), "confirm": (C,), "add_theme": (C,), "set_level": (F, C),
    "preview": (F, C, A), "media": (F, C, A), "get_wordlist": (F, C, A), "put_wordlist": (F, C, A),
    "status": STAFF, "segments": STAFF,
    # Running the pipeline is analyst work; the facilitator uploads, sets levels and enters attendance (PRD §3).
    "run_stage": (A,), "reset_job": (A,), "compare": (A,), "compare_with_reference": (A,),
    "unsupported": (A,), "names": (A,), "flags": (A,),
    "ask_question": STAFF, "list_concerns": STAFF, "raise_concern": STAFF, "sort_concern": STAFF,
    "artefacts": (F, C, A), "artefact_image": (F, C, A), "maker_statement": (F, C, A),
    "themes": (F, C, A), "units": (F, C, A), "job_audit": (F, C, A),
    "review": (C, A), "approve": (C, A), "export": (A, CL),
    "people_count": (A,), "add_name": (A,), "remove_name": (A,), "names_checked": (A,), "decide": (A,),
    "edit_report": (A,), "send": (A,),
    # Model names stay off every other role's screen: the facilitator doesn't need them.
    "model_settings": (A,), "set_model_settings": (A,),
}
_lock = threading.Lock()


# ---------- serialisers ----------

def _file(f: SourceFile) -> dict:
    return {"id": f.id, "filename": f.filename, "kind": f.kind, "level": f.level,
            "confirmed": f.level_confirmed_by_community, "names_checked": f.names_checked,
            "consent_id": f.consent_id, "provenance": f.provenance or {}}


def _segment(s: Segment) -> dict:
    return {"id": s.id, "file_id": s.file_id, "variant": s.variant, "start": s.start_s, "end": s.end_s,
            "speaker": s.speaker, "text": s.text, "confidence": s.confidence, "unsure": s.unsure}


def _theme(t: Theme) -> dict:
    return {"id": t.id, "label": t.label, "summary": t.summary, "status": t.status, "decided_by": t.decided_by,
            "n_people": t.n_people, "people_count": t.people_count, "agreed_upfront": t.agreed_upfront,
            "from_level3": t.from_level3, "level": t.level, "review_note": t.review_note,
            "quotes": [{"unit_id": q.unit_id, "text": q.unit.redacted_text, "speaker": q.unit.speaker_key,
                        "source_type": q.unit.source_type, "excluded": q.unit.excluded} for q in t.quotes]}


def _flag(f: IdentifyFlag, t: Theme) -> dict:
    return {"id": f.id, "theme_id": f.theme_id, "theme_label": t.label, "kind": f.kind, "detail": f.detail,
            "decision": f.decision, "reason": f.reason}


def _report(r: Report) -> dict:
    return {"id": r.id, "kind": r.kind, "markdown": r.markdown, "approved_community": r.approved_community,
            "approved_analyst": r.approved_analyst, "sent": r.sent}


def _concern(c: Concern) -> dict:
    return {"id": c.id, "stage": c.stage, "text": c.text, "category": c.category, "routed_to": c.routed_to,
            "level": c.level, "status": c.status, "created_at": c.created_at.isoformat() if c.created_at else None}


def _err(msg: str, code: int):
    return jsonify({"error": msg}), code


# ---------- app ----------

def _job_of(s, args: dict) -> int | None:
    """The job a request is about, from whatever id is in its URL."""
    if "job_id" in args:
        return args["job_id"]
    row = None
    if "file_id" in args:
        row = s.get(SourceFile, args["file_id"])
    elif "theme_id" in args:
        row = s.get(Theme, args["theme_id"])
    elif "report_id" in args:
        row = s.get(Report, args["report_id"])
    elif "art_id" in args:
        a = s.get(Artefact, args["art_id"])
        row = s.get(SourceFile, a.file_id) if a else None
    elif "flag_id" in args:
        f = s.get(IdentifyFlag, args["flag_id"])
        row = s.get(Theme, f.theme_id) if f else None
    elif "concern_id" in args:
        row = s.get(Concern, args["concern_id"])
    elif "name_id" in args:
        row = s.get(Pseudonym, args["name_id"])
    return row.job_id if row is not None else None


def create_app(testing: bool = False, auth_on: bool | None = None) -> Flask:
    app = Flask(__name__)
    auth_on = not testing if auth_on is None else auth_on
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
    upload_dir = settings.home / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    db.init_db()

    @app.errorhandler(s6_signoff.AuthorityError)
    def _authority(e):
        return _err(str(e), 409)

    @app.errorhandler(pipeline.GateError)
    def _gate(e):
        return _err(str(e), 409)

    @app.errorhandler(PermissionError)
    def _perm(e):
        return _err(str(e), 403)

    @app.errorhandler(ValueError)
    def _value(e):
        return _err(str(e), 400)

    @app.errorhandler(KeyError)
    def _key(e):
        return _err(f"not found: {e}", 404)

    @app.before_request
    def _sign_in_check():
        g.user = None
        if not auth_on or request.endpoint in ("health", "login") or request.method == "OPTIONS":
            return None
        # A header from the UI's server; ?t= on links the browser opens itself (photos, audio, downloads).
        header = request.headers.get("Authorization", "")
        token = header.removeprefix("Bearer ").strip() or request.args.get("t", "")
        with db.session() as s:
            user = auth.user_from_token(s, token)
            if user is None:
                return _err("please sign in", 401)
            g.user = auth.as_dict(user)
            if g.user["role"] not in PERMISSIONS.get(request.endpoint or "", ()):
                return _err(f"a {g.user['role']} can't do that", 403)
            mine = g.user["job_id"]
            if mine is not None and request.view_args:
                other = _job_of(s, request.view_args)
                if other is not None and other != mine:
                    return _err("that belongs to another job", 403)
        return None

    def _role(data: dict) -> str:
        """The caller's role: the signed-in account's, or (auth off, in tests) what the body says."""
        return g.user["role"] if g.user else data.get("actor_role", "")

    @app.post("/auth/login")
    def login():
        data = request.get_json(force=True) or {}
        with db.session() as s:
            user = auth.check_login(s, data.get("username", ""), data.get("password", ""))
            if user is None:
                return _err("that username and password don't match", 401)
            return jsonify({**auth.as_dict(user), "token": auth.make_token(user)})

    @app.get("/auth/me")
    def me():
        return jsonify(g.user or {})

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "model": settings.ollama_model, "vision_model": settings.ollama_vision_model,
                        "hf_token": bool(settings.hf_token)})

    # ---- jobs & files ----

    @app.post("/jobs")
    def create_job():
        data = request.get_json(force=True) or {}
        with db.session() as s:
            job = s0_intake.create_job(s, data.get("name", "Untitled job"), data.get("brief", ""))
            return jsonify({"id": job.id, "name": job.name}), 201

    @app.get("/jobs")
    def list_jobs():
        with db.session() as s:
            q = s.query(Job).order_by(Job.id)
            if g.user and g.user["job_id"] is not None:
                q = q.filter(Job.id == g.user["job_id"])
            return jsonify([{"id": j.id, "name": j.name, "status": j.status} for j in q])

    @app.get("/jobs/<int:job_id>")
    def get_job(job_id):
        with db.session() as s:
            j = s.get(Job, job_id)
            if j is None:
                return _err("no such job", 404)
            files = s.query(SourceFile).filter_by(job_id=job_id).order_by(SourceFile.id).all()
            return jsonify({"id": j.id, "name": j.name, "brief": j.brief, "status": j.status,
                            "attendance": j.attendance or [], "attendance_total": s0_intake.attendance_total(j),
                            "files": [_file(f) for f in files]})

    @app.put("/jobs/<int:job_id>/attendance")
    def set_attendance(job_id):
        data = request.get_json(force=True) or {}
        with db.session() as s:
            j = s0_intake.set_attendance(s, job_id, data.get("sessions", []))
            return jsonify({"attendance": j.attendance, "attendance_total": s0_intake.attendance_total(j)})

    @app.post("/jobs/<int:job_id>/agreed-themes")
    def add_agreed_theme(job_id):
        data = request.get_json(force=True) or {}
        with db.session() as s:
            t = s0_intake.add_agreed_theme(s, job_id, data.get("label", ""), data.get("summary", ""),
                                           level=int(data.get("level", 1)), actor_role=_role(data))
            return jsonify(_theme(t)), 201

    @app.post("/jobs/<int:job_id>/files")
    def upload(job_id):
        f = request.files.get("file")
        if f is None:
            return _err("no file", 400)
        level = int(request.form.get("level", "2"))
        dest = upload_dir / f"job{job_id}" / secure_filename(f.filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.save(dest)
        with db.session() as s:
            sf = s0_intake.add_file(s, job_id, dest, level=level,
                                    consent_label=request.form.get("consent_label", ""),
                                    consent_scope=request.form.get("consent_scope", ""))
            return jsonify(_file(sf)), 201

    @app.post("/jobs/<int:job_id>/files/local")
    def add_local(job_id):
        """Register a file already on disk (used by precompute and the demo)."""
        data = request.get_json(force=True)
        with db.session() as s:
            sf = s0_intake.add_file(s, job_id, Path(data["path"]), level=int(data.get("level", 2)),
                                    consent_label=data.get("consent_label", ""), consent_scope=data.get("consent_scope", ""))
            return jsonify(_file(sf)), 201

    @app.patch("/files/<int:file_id>/level")
    def set_level(file_id):
        data = request.get_json(force=True)
        with db.session() as s:
            sf = pipeline.raise_level(s, file_id, int(data["level"]))
            return jsonify(_file(sf))

    @app.post("/files/<int:file_id>/confirm")
    def confirm(file_id):
        with db.session() as s:
            return jsonify(_file(s0_intake.confirm_level(s, file_id)))

    def _preview_path(f: SourceFile) -> Path:
        return Path((f.provenance or {}).get("ingested_path") or f.path)

    @app.get("/files/<int:file_id>/preview")
    def preview(file_id):
        """What a community reviewer looks at before confirming a level. No AI: the
        file itself, or the words stage 1 pulled out of it."""
        with db.session() as s:
            f = s.get(SourceFile, file_id)
            if f is None:
                return _err("not found", 404)
            text = ""
            if f.kind == "text":
                p = _preview_path(f)
                if p.suffix.lower() in (".txt", ".md") and p.exists():
                    text = p.read_text(encoding="utf-8", errors="replace")[:600]
            return jsonify({"id": f.id, "kind": f.kind, "text": text})

    @app.get("/files/<int:file_id>/media")
    def media(file_id):
        with db.session() as s:
            f = s.get(SourceFile, file_id)
            if f is None:
                return _err("not found", 404)
            p = _preview_path(f)
        if not p.exists():
            return _err("file is missing on disk", 404)
        return send_file(p, mimetype=mimetypes.guess_type(p.name)[0] or "application/octet-stream")

    # ---- running stages ----

    def _run_in_thread(job_id: int, n: int, opts: dict):
        with _lock:
            RUNS[job_id] = {"stage": n, "started": time.time(), "finished": None, "error": None, "result": None}
        try:
            with db.session() as s:
                result = pipeline.run_stage(s, job_id, n, **opts)
            with _lock:
                RUNS[job_id].update(finished=time.time(), result=result)
        except Exception as e:  # noqa: BLE001 — surfaced to the UI
            with _lock:
                RUNS[job_id].update(finished=time.time(), error=f"{type(e).__name__}: {e}")
            traceback.print_exc()

    @app.post("/jobs/<int:job_id>/run/<int:n>")
    def run_stage(job_id, n):
        opts = request.get_json(silent=True) or {}
        with db.session() as s:  # check gates now so the caller gets the 409, not the thread
            pipeline._check_gates(s, job_id, n)
            if s.get(Job, job_id) is None:
                return _err("no such job", 404)
        with _lock:
            r = RUNS.get(job_id)
            if r and r["finished"] is None:
                return _err(f"stage {r['stage']} is still running", 409)
        if testing:
            _run_in_thread(job_id, n, opts)
        else:
            threading.Thread(target=_run_in_thread, args=(job_id, n, opts), daemon=True).start()
        return jsonify({"job_id": job_id, "stage": n, "started": True}), 202

    @app.post("/jobs/<int:job_id>/reset")
    def reset_job(job_id):
        """Back to intake: every stage's output goes, the uploaded files and their consent/levels stay."""
        with _lock:
            r = RUNS.get(job_id)
            if r and r["finished"] is None:
                return _err(f"stage {r['stage']} is still running — wait for it to finish", 409)
            RUNS.pop(job_id, None)
        with db.session() as s:
            return jsonify(pipeline.reset_job(s, job_id, exports_dir=settings.home / "exports"))

    @app.get("/jobs/<int:job_id>/status")
    def status(job_id):
        with db.session() as s:
            st = pipeline.status(s, job_id)
        with _lock:
            st["run"] = RUNS.get(job_id)
        return jsonify(st)

    # ---- stage views ----

    @app.get("/jobs/<int:job_id>/segments")
    def segments(job_id):
        variant = request.args.get("variant", "with_wordlist")
        with db.session() as s:
            rows = (s.query(Segment).join(SourceFile).filter(SourceFile.job_id == job_id, Segment.variant == variant)
                    .order_by(Segment.file_id, Segment.start_s).all())
            return jsonify([_segment(r) for r in rows])

    @app.get("/jobs/<int:job_id>/compare/<int:file_id>")
    def compare(job_id, file_id):
        ref = request.args.get("reference")
        with db.session() as s:
            return jsonify(s2_transcribe.compare(s, file_id, reference=ref))

    @app.post("/jobs/<int:job_id>/compare/<int:file_id>")
    def compare_with_reference(job_id, file_id):
        data = request.get_json(force=True) or {}
        with db.session() as s:
            return jsonify(s2_transcribe.compare(s, file_id, reference=data.get("reference")))

    @app.get("/jobs/<int:job_id>/artefacts")
    def artefacts(job_id):
        with db.session() as s:
            rows = (s.query(Artefact, SourceFile).join(SourceFile, SourceFile.id == Artefact.file_id)
                    .filter(SourceFile.job_id == job_id).all())
            return jsonify([{"id": a.id, "file_id": f.id, "filename": f.filename, "level": f.level,
                             "image_path": (f.provenance or {}).get("ingested_path", f.path),
                             "verbatim_text": a.verbatim_text, "description": a.description,
                             "illegible_count": a.illegible_count, "maker_statement": a.maker_statement}
                            for a, f in rows])

    @app.get("/artefacts/<int:art_id>/image")
    def artefact_image(art_id):
        with db.session() as s:
            a = s.get(Artefact, art_id)
            f = s.get(SourceFile, a.file_id) if a else None
            if f is None:
                return _err("not found", 404)
            p = (f.provenance or {}).get("ingested_path") or f.path
        return send_file(p, mimetype="image/jpeg")

    @app.patch("/artefacts/<int:art_id>")
    def maker_statement(art_id):
        data = request.get_json(force=True)
        with db.session() as s:
            a = s.get(Artefact, art_id)
            if a is None:
                return _err("not found", 404)
            a.maker_statement = data.get("maker_statement", "")
            return jsonify({"id": a.id, "maker_statement": a.maker_statement})

    @app.get("/jobs/<int:job_id>/themes")
    def themes(job_id):
        with db.session() as s:
            rows = (s.query(Theme).filter(Theme.job_id == job_id, Theme.status != "unsupported")
                    .order_by(Theme.n_people.desc(), Theme.id).all())
            return jsonify([_theme(t) for t in rows])

    @app.get("/jobs/<int:job_id>/themes/unsupported")
    def unsupported(job_id):
        """Analyst-only view of what the evidence check threw out, and why."""
        with db.session() as s:
            rows = s.query(Theme).filter_by(job_id=job_id, status="unsupported").all()
            return jsonify([{"id": t.id, "label": t.label, "review_note": t.review_note} for t in rows])

    @app.patch("/themes/<int:theme_id>")
    def review(theme_id):
        data = request.get_json(force=True)
        with db.session() as s:
            t = s6_signoff.review(s, theme_id, actor_role=_role(data), action=data["action"],
                                  label=data.get("label"), summary=data.get("summary"), note=data.get("note", ""))
            return jsonify(_theme(t))

    @app.post("/jobs/<int:job_id>/themes")
    def add_theme(job_id):
        data = request.get_json(force=True)
        with db.session() as s:
            t = s6_signoff.add_theme(s, job_id, data["label"], data.get("summary", ""), data.get("quote_unit_ids", []),
                                     from_level3=bool(data.get("from_level3")), level=int(data.get("level", 1)))
            return jsonify(_theme(t)), 201

    @app.patch("/themes/<int:theme_id>/people")
    def people_count(theme_id):
        data = request.get_json(force=True)
        with db.session() as s:
            t = s6_signoff.set_people_count(s, theme_id, data["count"], actor_role=_role(data))
            return jsonify(_theme(t))

    # ---- Level 2 names (stage 4) ----

    def _names(s, job_id):
        files = (s.query(SourceFile).filter_by(job_id=job_id, level=2).order_by(SourceFile.id).all())
        units = s.query(Unit).filter_by(job_id=job_id, level=2, excluded=False).order_by(Unit.id).all()
        return {
            "names": [{"id": p.id, "real": p.real, "fake": p.fake, "source": p.source}
                      for p in s.query(Pseudonym).filter_by(job_id=job_id).order_by(Pseudonym.id)],
            "files": [{"id": f.id, "filename": f.filename, "names_checked": f.names_checked,
                       "units": [{"id": u.id, "text": u.redacted_text} for u in units if u.file_id == f.id]}
                      for f in files],
            "waiting": s4_themes.waiting_name_check(s, job_id),
        }

    @app.get("/jobs/<int:job_id>/names")
    def names(job_id):
        with db.session() as s:
            return jsonify(_names(s, job_id))

    @app.post("/jobs/<int:job_id>/names")
    def add_name(job_id):
        data = request.get_json(force=True) or {}
        with db.session() as s:
            if s4_themes.add_name(s, job_id, data.get("real", ""), "person") is None:
                return _err("that name is empty or already on the list", 400)
            s4_themes.names_changed(s, job_id)
            return jsonify(_names(s, job_id)), 201

    @app.delete("/names/<int:name_id>")
    def remove_name(name_id):
        with db.session() as s:
            p = s.get(Pseudonym, name_id)
            if p is None:
                return _err("not found", 404)
            job_id = p.job_id
            s.delete(p)
            s.flush()
            s4_themes.names_changed(s, job_id)
            return jsonify(_names(s, job_id))

    @app.post("/files/<int:file_id>/names-checked")
    def names_checked(file_id):
        with db.session() as s:
            return jsonify(_file(s4_themes.set_names_checked(s, file_id)))

    @app.get("/jobs/<int:job_id>/units")
    def units(job_id):
        with db.session() as s:
            rows = s.query(Unit).filter_by(job_id=job_id, excluded=False).order_by(Unit.id).all()
            return jsonify([{"id": u.id, "text": u.redacted_text, "speaker": u.speaker_key, "source_type": u.source_type}
                            for u in rows])

    @app.get("/jobs/<int:job_id>/flags")
    def flags(job_id):
        with db.session() as s:
            rows = (s.query(IdentifyFlag, Theme).join(Theme, Theme.id == IdentifyFlag.theme_id)
                    .filter(Theme.job_id == job_id).order_by(IdentifyFlag.id).all())
            return jsonify([_flag(f, t) for f, t in rows])

    @app.post("/flags/<int:flag_id>/decide")
    def decide(flag_id):
        data = request.get_json(force=True)
        with db.session() as s:
            f = s7_identify.decide(s, flag_id, data["decision"], reason=data.get("reason", ""))
            return jsonify(_flag(f, s.get(Theme, f.theme_id)))

    @app.get("/jobs/<int:job_id>/reports")
    def reports(job_id):
        with db.session() as s:
            rows = s.query(Report).filter_by(job_id=job_id).all()
            if g.user and g.user["role"] == "client":  # the client sees the finished report, nothing before it
                rows = [r for r in rows if r.kind == "client" and r.approved_community and r.approved_analyst]
            return jsonify([_report(r) for r in rows])

    @app.patch("/reports/<int:report_id>")
    def edit_report(report_id):
        data = request.get_json(force=True)
        with db.session() as s:
            return jsonify(_report(s8_report.edit(s, report_id, data["markdown"])))

    @app.post("/reports/<int:report_id>/approve")
    def approve(report_id):
        data = request.get_json(force=True)
        with db.session() as s:
            return jsonify(_report(s8_report.approve(s, report_id, _role(data))))

    @app.get("/reports/<int:report_id>/export")
    def export(report_id):
        with db.session() as s:
            _md, docx = s8_report.export(s, report_id, settings.home / "exports")
        return send_file(docx, as_attachment=True, download_name=docx.name,
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    @app.post("/reports/<int:report_id>/send")
    def send(report_id):
        with db.session() as s:
            return jsonify(_report(s9_reportback.send(s, report_id)))

    # ---- chat with the data (PRD A19) ----

    @app.post("/jobs/<int:job_id>/ask")
    def ask_question(job_id):
        data = request.get_json(force=True) or {}
        with _lock:
            r = RUNS.get(job_id)
            if r and r["finished"] is None:
                # the laptop can't hold the stage's model and the text model at once
                return _err(f"stage {r['stage']} is running — ask again when it finishes", 409)
        with db.session() as s:
            return jsonify(ask.ask(s, job_id, data.get("question", ""), actor_role=_role(data),
                                   history=data.get("history") or []))

    # ---- concerns ----

    @app.post("/jobs/<int:job_id>/concerns")
    def raise_concern(job_id):
        data = request.get_json(force=True)
        with db.session() as s:
            c = concerns.raise_concern(s, job_id, stage=int(data.get("stage", 0)), text=data.get("text", ""))
            return jsonify(_concern(c)), 201

    @app.get("/jobs/<int:job_id>/concerns")
    def list_concerns(job_id):
        with db.session() as s:
            return jsonify([_concern(c) for c in s.query(Concern).filter_by(job_id=job_id).order_by(Concern.id)])

    @app.post("/concerns/<int:concern_id>/sort")
    def sort_concern(concern_id):
        data = request.get_json(force=True)
        with db.session() as s:
            c = concerns.sort_concern(s, concern_id, data["category"], material_level=data.get("material_level"))
            return jsonify(_concern(c))

    # ---- which model each step uses (the analyst's) ----

    @app.get("/jobs/<int:job_id>/models")
    def model_settings(job_id):
        have = model_choice.available()
        with db.session() as s:
            if s.get(Job, job_id) is None:
                return _err("no such job", 404)
            done = {int(st["n"]): bool(st["done"]) for st in pipeline.status(s, job_id).get("stages", [])}
            steps = []
            for n, (name, kind, does) in model_choice.STEPS.items():
                options = [{**m, "heavy": m["size_gb"] > model_choice.MEMORY_WARN_GB} for m in have[kind]]
                chosen = model_choice.chosen(s, job_id, n)
                steps.append({"stage": n, "name": name, "kind": kind, "does": does,
                              "chosen": chosen, "chosen_display": model_choice.display_name(kind, chosen),
                              "default": model_choice.default_for(n),
                              "done": done.get(n, False), "options": options})
        return jsonify({"steps": steps, "ollama_error": have["ollama_error"],
                        "memory_warn_gb": model_choice.MEMORY_WARN_GB})

    @app.put("/jobs/<int:job_id>/models")
    def set_model_settings(job_id):
        data = request.get_json(force=True) or {}
        with db.session() as s:
            return jsonify({"models": model_choice.set_choices(s, job_id, data.get("models", {}))})

    # ---- audit & word list ----

    @app.get("/jobs/<int:job_id>/audit")
    def job_audit(job_id):
        with db.session() as s:
            return jsonify(audit.summary(s, job_id))

    @app.get("/wordlist")
    def get_wordlist():
        p = settings.wordlist_path
        return jsonify({"text": p.read_text(encoding="utf-8") if p.exists() else "",
                        "words": load_wordlist(p), "persons": person_names(p)})

    @app.put("/wordlist")
    def put_wordlist():
        data = request.get_json(force=True)
        save_wordlist(settings.wordlist_path, data.get("text", ""))
        return get_wordlist()

    return app


def main():
    app = create_app()
    print(f"VCNITY API on http://127.0.0.1:{settings.api_port}  "
          f"(text: {settings.ollama_model} · vision: {settings.ollama_vision_model} — never loaded together, "
          f"HF token {'present' if settings.hf_token else 'absent'})")
    app.run(host="127.0.0.1", port=settings.api_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
