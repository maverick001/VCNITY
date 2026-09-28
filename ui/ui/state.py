"""One state for the whole UI. Every handler talks to the API and reloads."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import reflex as rx

from . import api_client as api
from .api_client import ApiError

ROLES = ["facilitator", "community", "analyst", "client"]
# Stage 1 is Data Ingest: PRD §4's Intake (stage 0) and Ingest (stage 1) merged.
STAGE_ROUTES = {1: "/", 2: "/transcript", 3: "/artefacts", 4: "/themes", 5: "/themes",
                6: "/signoff", 7: "/identify", 8: "/report", 9: "/reportback"}
# Left out of the sidebar and Overview. Report back isn't on the client's slides; it stays reachable at
# /reportback until the client says what slide 11's "reporting function" means (PRD A14).
HIDDEN_STAGES = {9}

# PRD v1.1 §4, the pipeline table: what the AI does and what a person does at each stage.
STAGE_INFO = {
    1: ("Converts formats and records where each file came from. Pulls the words out of slides, Word and "
        "text files.",
        "Ties every file to a consent record and a sensitivity level — nothing gets in without both. "
        "Enters who came to each session, and agrees the set of themes with the community."),
    2: ("Speech to text, works out who's speaking, copes with different languages and accents, and scores how "
        "sure it is.", "The community gives a word list — names, slang, local place words. Anything below 0.6 "
                       "confidence goes to a person."),
    3: ("Describes what's in the photo, nothing more.",
        "Meaning comes from what the maker said about their own work. AI never guesses what art means."),
    4: ("For Level 2, swaps real names for made-up ones. Sorts material into the agreed themes and suggests new "
        "draft themes for the rest.", "A person checks the swapped names on Level 2 before sorting starts."),
    5: ("Checks every claim traces to a real quote and throws out the ones that don't.", "—"),
    6: ("—", "The community confirms, fixes, rejects, or adds what we missed. What they say goes."),
    7: ("Flags themes that come from very few people, and anything that gives someone away.",
        "The analyst counts the people behind each theme by hand, decides what to cut, and writes down why."),
    8: ("Drafts recommendations against the brief.",
        "The analyst edits. Community and analyst both approve before it leaves."),
    9: ("Drafts a plain-language version for participants.", "The analyst approves and sends it."),
}


class AppState(rx.State):
    # who / where
    role: str = "facilitator"
    job_id: int = 0
    jobs: list[dict[str, Any]] = []
    job: dict[str, Any] = {}
    message: str = ""
    message_kind: str = "info"  # info | error | ok

    # status & audit
    status: dict[str, Any] = {}
    stages: list[dict[str, Any]] = []
    run: dict[str, Any] = {}
    running: bool = False
    audit: dict[str, Any] = {"level3_calls": 0, "hosted_calls_l2plus": 0, "total": 0}

    # intake
    files: list[dict[str, Any]] = []
    wordlist_text: str = ""
    upload_level: str = "2"
    upload_consent_label: str = ""
    upload_consent_scope: str = ""
    uploading: bool = False
    upload_error: str = ""
    attendance: list[dict[str, Any]] = []
    att_session: str = ""
    att_count: str = ""
    agreed_label: str = ""
    agreed_summary: str = ""
    agreed_level: str = "1"

    # Level 2 names (stage 4)
    names: list[dict[str, Any]] = []
    name_files: list[dict[str, Any]] = []
    new_name: str = ""

    # transcript
    audio_files: list[dict[str, Any]] = []
    selected_file_id: int = 0
    segments_with: list[dict[str, Any]] = []
    segments_without: list[dict[str, Any]] = []
    compare: dict[str, Any] = {}
    diff: list[dict[str, Any]] = []
    reference_text: str = ""

    # artefacts
    artefacts: list[dict[str, Any]] = []
    maker_edit_id: int = 0
    maker_edit_text: str = ""

    # themes / sign-off
    themes: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    fix_id: int = 0
    fix_label: str = ""
    fix_summary: str = ""
    fix_note: str = ""
    add_label: str = ""
    add_summary: str = ""
    add_quote_ids: str = ""
    add_from_level3: bool = False
    add_level: str = "1"

    # identify
    flags: list[dict[str, Any]] = []
    flag_reason: str = ""
    flag_edit_id: int = 0

    # reports
    client_report: dict[str, Any] = {}
    reportback: dict[str, Any] = {}

    # concerns (no UI to raise one for now; kept so earlier concerns still load)
    concerns: list[dict[str, Any]] = []
    concern_text: str = ""
    concern_stage: str = "0"
    concern_open: bool = False

    # chat with the data (PRD A19) — kept only until the page reloads
    chat: list[dict[str, Any]] = []
    chat_input: str = ""
    chat_busy: bool = False

    # ---------- helpers ----------

    def _say(self, msg: str, kind: str = "info"):
        self.message = msg
        self.message_kind = kind

    def _api(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ApiError as e:
            self._say(f"{e.status}: {e.message}", "error")
        except Exception as e:  # noqa: BLE001
            self._say(f"API not reachable: {e}", "error")
        return None

    @rx.var
    def export_url(self) -> str:
        return api.export_url(int(self.client_report.get("id", 0))) if self.client_report else ""

    @rx.var
    def can_export(self) -> bool:
        r = self.client_report
        return bool(r) and bool(r.get("approved_community")) and bool(r.get("approved_analyst"))

    @rx.var
    def can_send(self) -> bool:
        r = self.reportback  # PRD stage 9: the analyst approves and sends it
        return bool(r) and bool(r.get("approved_analyst")) and not r.get("sent")

    @rx.var
    def can_ask(self) -> bool:
        return self.role in ("facilitator", "analyst") and bool(self.job_id)

    @rx.var
    def chat_url(self) -> str:
        # A new tab starts with fresh state, so the job and role travel in the link.
        return f"/chat?job={self.job_id}&role={self.role}"

    @rx.var
    def audit_ok(self) -> bool:
        return int(self.audit.get("level3_calls", 0)) == 0 and int(self.audit.get("hosted_calls_l2plus", 0)) == 0

    @rx.var
    def waiting_level2_text(self) -> str:
        return ", ".join(self.status.get("waiting_level2", []))

    @rx.var
    def has_waiting_level2(self) -> bool:
        return bool(self.status.get("waiting_level2"))

    @rx.var
    def waiting_names_text(self) -> str:
        return ", ".join(self.status.get("waiting_names", []))

    @rx.var
    def has_waiting_names(self) -> bool:
        return bool(self.status.get("waiting_names"))

    @rx.var
    def attendance_total_text(self) -> str:
        return f"{self.status.get('attendance_total', 0)} people in total"

    @rx.var
    def uncounted_text(self) -> str:
        return ", ".join(self.status.get("uncounted", []))

    @rx.var
    def has_uncounted(self) -> bool:
        return bool(self.status.get("uncounted"))

    @rx.var
    def agreed_themes(self) -> list[dict[str, Any]]:
        return [t for t in self.themes if t.get("agreed_upfront")]

    @rx.var
    def signed_off_themes(self) -> list[dict[str, Any]]:
        return [t for t in self.themes if t.get("status") in ("confirmed", "fixed", "added")]

    @rx.var
    def has_name_files(self) -> bool:
        return bool(self.name_files)

    @rx.var
    def job_options(self) -> list[str]:
        return [str(j["id"]) for j in self.jobs]

    @rx.var
    def audio_options(self) -> list[str]:
        return [str(f["id"]) for f in self.audio_files]

    @rx.var
    def has_client_report(self) -> bool:
        return bool(self.client_report.get("id"))

    @rx.var
    def has_reportback(self) -> bool:
        return bool(self.reportback.get("id"))

    @rx.var
    def has_reference_wer(self) -> bool:
        return "wer_with_vs_reference" in self.compare

    @rx.var
    def run_stage_text(self) -> str:
        return str(self.run.get("stage", ""))

    @rx.var
    def run_elapsed_text(self) -> str:
        started = self.run.get("started")
        if not started:
            return "just started"
        m, s = divmod(max(0, int(time.time() - started)), 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"

    @rx.var
    def status_line(self) -> str:
        s = self.status
        return (f"files {s.get('files', 0)} · segments {s.get('segments', 0)} · units {s.get('units', 0)} · "
                f"themes {s.get('themes', 0)} · open flags {s.get('open_flags', 0)}")

    @rx.var
    def compare_line(self) -> str:
        c = self.compare
        if not c:
            return "No transcript yet."
        return (f"Words changed: {c.get('words_changed', 0)} of {c.get('words_total', 0)} · "
                f"distance between runs: {c.get('wer_between_runs', 0)}")

    @rx.var
    def compare_note(self) -> str:
        return str(self.compare.get("note", ""))

    @rx.var
    def reference_wer_line(self) -> str:
        c = self.compare
        if "wer_with_vs_reference" not in c:
            return ""
        return f"WER without word list {c['wer_without_vs_reference']} → with word list {c['wer_with_vs_reference']}"

    @rx.var
    def terms_line(self) -> str:
        c = self.compare
        w, wo = c.get("wordlist_terms_with") or {}, c.get("wordlist_terms_without") or {}
        if not w.get("in_reference"):
            return ""
        return (f"Word-list terms in the reference: {w['in_reference']} · got right without the list "
                f"{wo.get('found', 0)}, with it {w.get('found', 0)} (term error rate {wo.get('error_rate')} → "
                f"{w.get('error_rate')})")

    @rx.var
    def audit_total_text(self) -> str:
        return f"{self.audit.get('total', 0)} model calls logged"

    @rx.var
    def unsupported_count(self) -> int:
        return len(self.unsupported)

    @rx.var
    def job_brief(self) -> str:
        return str(self.job.get("brief", ""))

    @rx.var
    def stage_names(self) -> list[dict[str, Any]]:
        out = []
        for s in self.stages:
            n = int(s["n"])
            if n in HIDDEN_STAGES:
                continue
            ai, person = STAGE_INFO.get(n, ("", ""))
            out.append({**s, "route": STAGE_ROUTES.get(n, "/"), "has_route": bool(STAGE_ROUTES.get(n)),
                        "ai": ai, "person": person, "waiting": s.get("waiting", ""),
                        "is_waiting": bool(s.get("waiting"))})
        return out

    # ---------- loading ----------

    def load_all(self):
        self.message = ""
        jobs = self._api(api.get, "/jobs")
        if jobs is None:
            return
        self.jobs = jobs
        if not self.job_id and jobs:
            self.job_id = int(jobs[-1]["id"])
        if not self.job_id:
            self._say("No job yet. Run app/scripts/precompute.py or create one below.")
            return
        self.refresh()

    def refresh(self):
        j = self._api(api.get, f"/jobs/{self.job_id}")
        if j is None:
            return
        self.job = j
        self.attendance = [{**r, "i": i, "line": f"{r['session']}: {r['count']}"}
                           for i, r in enumerate(j.get("attendance", []))]
        self.files = j.get("files", [])
        self.audio_files = [f for f in self.files if f["kind"] == "audio"]
        st = self._api(api.get, f"/jobs/{self.job_id}/status") or {}
        self.status = st
        self.stages = st.get("stages", [])
        self.run = st.get("run") or {}
        self.running = bool(self.run) and self.run.get("finished") is None
        self.audit = self._api(api.get, f"/jobs/{self.job_id}/audit") or self.audit
        wl = self._api(api.get, "/wordlist") or {}
        self.wordlist_text = wl.get("text", "")
        self.files = [{**f, "level_text": str(f["level"]), "consent_text": f"consent #{f['consent_id']}",
                       "id_text": str(f["id"])} for f in self.files]
        self.audio_files = [f for f in self.files if f["kind"] == "audio"]
        self.artefacts = [{**a, "image_url": api.image_url(int(a["id"])),
                           "illegible_text": f"{a['illegible_count']} illegible",
                           "maker_text": a["maker_statement"] or "—"}
                          for a in (self._api(api.get, f"/jobs/{self.job_id}/artefacts") or [])]
        self.themes = [self._shape_theme(t) for t in (self._api(api.get, f"/jobs/{self.job_id}/themes") or [])]
        self.unsupported = [{**u, "line": f"{u['label']} — {u['review_note']}"}
                            for u in (self._api(api.get, f"/jobs/{self.job_id}/themes/unsupported") or [])]
        nm = self._api(api.get, f"/jobs/{self.job_id}/names") or {}
        self.names = [{**n, "line": f"{n['real']} → {n['fake']}  ({n['source']})"} for n in nm.get("names", [])]
        self.name_files = [{**f, "units": [{**u, "line": f"#{u['id']} {u['text']}"} for u in f["units"]],
                            "units_header": f"What sorting will see ({len(f['units'])})"}
                           for f in nm.get("files", []) if f["units"]]
        self.units = [{**u, "line": f"#{u['id']} [{u['speaker']}] {u['text']}"}
                      for u in (self._api(api.get, f"/jobs/{self.job_id}/units") or [])]
        self.flags = [{**f, "decision_text": f"Decision: {f['decision']} — {f['reason']}" if f["decision"] else ""}
                      for f in (self._api(api.get, f"/jobs/{self.job_id}/flags") or [])]
        reps = self._api(api.get, f"/jobs/{self.job_id}/reports") or []
        self.client_report = next((r for r in reps if r["kind"] == "client"), {})
        self.reportback = next((r for r in reps if r["kind"] == "reportback"), {})
        self.concerns = [{**c, "stage_text": f"stage {c['stage']}",
                          "routed_text": f"Routed to: {c['routed_to']} · treated as Level {c['level']}" if c["routed_to"] else ""}
                         for c in (self._api(api.get, f"/jobs/{self.job_id}/concerns") or [])]
        if self.audio_files and not self.selected_file_id:
            self.selected_file_id = int(self.audio_files[0]["id"])
        if self.selected_file_id:
            self._load_transcript()

    @staticmethod
    def _shape_theme(t: dict) -> dict:
        quotes = [{**q, "id_text": f"#{q['unit_id']}"} for q in t.get("quotes", [])]
        counted = t.get("people_count")
        people = f"{counted} people (counted)" if counted is not None else f"{t['n_people']} voices heard — not counted"
        return {**t, "quotes": quotes, "quotes_header": f"Quotes ({len(quotes)})",
                "people_text": people, "count_text": "" if counted is None else str(counted),
                "has_note": bool(t.get("review_note"))}

    @staticmethod
    def _shape_segment(s: dict) -> dict:
        return {**s, "start_text": f"{s['start']:.1f}", "speaker_text": s["speaker"] or "?"}

    def _load_transcript(self):
        fid = self.selected_file_id
        allw = self._api(api.get, f"/jobs/{self.job_id}/segments", variant="with_wordlist") or []
        allo = self._api(api.get, f"/jobs/{self.job_id}/segments", variant="without") or []
        self.segments_with = [self._shape_segment(s) for s in allw if s["file_id"] == fid]
        self.segments_without = [self._shape_segment(s) for s in allo if s["file_id"] == fid]
        cmp = self._api(api.get, f"/jobs/{self.job_id}/compare/{fid}") or {}
        self.compare = {k: v for k, v in cmp.items() if k != "diff"}
        self.diff = cmp.get("diff", [])

    def poll(self):
        """Called by the pipeline page while a stage runs."""
        if not self.job_id:
            return
        st = self._api(api.get, f"/jobs/{self.job_id}/status") or {}
        self.run = st.get("run") or {}
        was_running = self.running
        self.running = bool(self.run) and self.run.get("finished") is None
        if was_running and not self.running:
            if self.run.get("error"):
                self._say(f"Stage {self.run.get('stage')} failed: {self.run['error']}", "error")
            else:
                self._say(f"Stage {self.run.get('stage')} finished in {self.run.get('result', {}).get('seconds', '?')} s", "ok")
            self.refresh()

    # ---------- simple setters ----------

    def set_role(self, v: str):
        self.role = v

    def select_job(self, v: str):
        self.job_id = int(v)
        self.selected_file_id = 0
        self.chat = []
        self.refresh()

    def set_wordlist_text(self, v: str):
        self.wordlist_text = v

    def set_reference_text(self, v: str):
        self.reference_text = v

    def set_maker_edit_text(self, v: str):
        self.maker_edit_text = v

    def set_fix_label(self, v: str):
        self.fix_label = v

    def set_fix_summary(self, v: str):
        self.fix_summary = v

    def set_fix_note(self, v: str):
        self.fix_note = v

    def set_add_label(self, v: str):
        self.add_label = v

    def set_add_summary(self, v: str):
        self.add_summary = v

    def set_add_quote_ids(self, v: str):
        self.add_quote_ids = v

    def set_add_from_level3(self, v: bool):
        self.add_from_level3 = v

    def set_add_level(self, v: str):
        self.add_level = v

    def set_att_session(self, v: str):
        self.att_session = v

    def set_att_count(self, v: str):
        self.att_count = v

    def set_agreed_label(self, v: str):
        self.agreed_label = v

    def set_agreed_summary(self, v: str):
        self.agreed_summary = v

    def set_agreed_level(self, v: str):
        self.agreed_level = v

    def set_new_name(self, v: str):
        self.new_name = v

    def set_flag_reason(self, v: str):
        self.flag_reason = v

    def set_concern_text(self, v: str):
        self.concern_text = v

    def set_concern_stage(self, v: str):
        self.concern_stage = v

    def set_concern_open(self, v: bool):
        self.concern_open = v

    # ---------- intake ----------

    def create_job(self):
        j = self._api(api.post, "/jobs", {"name": "New job"})
        if j:
            self.job_id = int(j["id"])
            self.load_all()

    def set_file_level(self, file_id: int, level: str):
        out = self._api(api.patch, f"/files/{int(file_id)}/level", {"level": int(level), "actor_role": self.role})
        if out is not None:
            self._say(f"Level set to {level}. " + ("Material withdrawn from AI outputs." if int(level) == 3 else
                                                  "A community reviewer must confirm before AI runs."), "ok")
            self.refresh()

    def confirm_file(self, file_id: int):
        if self.role != "community":
            self._say("Only a community reviewer confirms a level (PRD A9). Switch role at the top.", "error")
            return
        if self._api(api.post, f"/files/{int(file_id)}/confirm") is not None:
            self._say("Level confirmed by the community.", "ok")
            self.refresh()

    def save_wordlist(self):
        if self._api(api.put, "/wordlist", {"text": self.wordlist_text}) is not None:
            self._say("Word list saved. Re-run stage 2 to use it.", "ok")

    def set_upload_level(self, v: str):
        self.upload_level = v

    def set_upload_consent_label(self, v: str):
        self.upload_consent_label = v

    def set_upload_consent_scope(self, v: str):
        self.upload_consent_scope = v

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Facilitator uploads audio, images, or office documents onto the job.
        Every file still needs a consent record and a level before it counts as
        intake (PRD §4 stage 0) — that's enforced by the API, not just this form.
        """
        # This handler is an async generator (it yields further down), so every
        # early-return branch must yield too — otherwise Reflex never flushes
        # that state change to the browser and the page looks like nothing happened.
        if self.role != "facilitator":
            self._say("Only a facilitator uploads files (PRD §3). Switch role at the top.", "error")
            yield
            return
        if not self.job_id:
            self._say("Create a job first.", "error")
            yield
            return
        if not self.upload_consent_label.strip():
            self.upload_error = "A consent record needs a label — who or what session this covers."
            yield
            return
        self.upload_error = ""
        self.uploading = True
        yield
        ok, failed = 0, []
        for f in files:
            content = await f.read()
            try:
                api.upload_file(
                    f"/jobs/{self.job_id}/files", filename=f.filename or "upload", content=content,
                    level=int(self.upload_level), consent_label=self.upload_consent_label,
                    consent_scope=self.upload_consent_scope,
                )
                ok += 1
            except ApiError as e:
                failed.append(f"{f.filename}: {e.message}")
            except Exception as e:  # noqa: BLE001
                failed.append(f"{f.filename}: {e}")
        self.uploading = False
        if ok and not failed:
            self._say(f"Uploaded {ok} file(s) at Level {self.upload_level}. "
                      "A community reviewer still needs to confirm before AI runs on them.", "ok")
        elif ok:
            self._say(f"Uploaded {ok} file(s); {len(failed)} failed: " + "; ".join(failed), "error")
        else:
            self._say("Upload failed: " + "; ".join(failed), "error")
        self.refresh()
        yield rx.clear_selected_files("facilitator_upload")

    def _put_attendance(self, rows: list[dict]) -> bool:
        out = self._api(api.put, f"/jobs/{self.job_id}/attendance",
                        {"sessions": [{"session": r["session"], "count": r["count"]} for r in rows]})
        if out is not None:
            self.refresh()
        return out is not None

    def add_attendance(self):
        if self.role != "facilitator":
            self._say("The facilitator enters attendance (PRD §4 stage 0). Switch role at the top.", "error")
            return
        rows = [*self.attendance, {"session": self.att_session, "count": self.att_count}]
        if self._put_attendance(rows):
            self._say("Attendance saved.", "ok")
            self.att_session = self.att_count = ""

    def remove_attendance(self, i: int):
        if self.role != "facilitator":
            self._say("The facilitator enters attendance. Switch role at the top.", "error")
            return
        self._put_attendance([r for r in self.attendance if int(r["i"]) != int(i)])

    def add_agreed_theme(self):
        out = self._api(api.post, f"/jobs/{self.job_id}/agreed-themes",
                        {"label": self.agreed_label, "summary": self.agreed_summary,
                         "level": int(self.agreed_level), "actor_role": self.role})
        if out is not None:
            self._say("Theme agreed. Stage 4 will sort material into it.", "ok")
            self.agreed_label = self.agreed_summary = ""
            self.refresh()

    # ---------- Level 2 names ----------

    def add_name(self):
        if self._api(api.post, f"/jobs/{self.job_id}/names", {"real": self.new_name}) is not None:
            self._say("Name added. Every Level 2 file needs checking again.", "ok")
            self.new_name = ""
            self.refresh()

    def remove_name(self, name_id: int):
        if self._api(api.delete, f"/names/{int(name_id)}") is not None:
            self._say("Name removed. Every Level 2 file needs checking again.", "ok")
            self.refresh()

    def mark_names_checked(self, file_id: int):
        if self._api(api.post, f"/files/{int(file_id)}/names-checked") is not None:
            self._say("Names checked. Re-run stage 4 to sort once every Level 2 file is checked.", "ok")
            self.refresh()

    # ---------- pipeline ----------

    def reset_job(self):
        out = self._api(api.post, f"/jobs/{self.job_id}/reset")
        if out is not None:
            self._say(f"Job reset to intake: {out['themes_removed']} theme(s) and every stage's output removed. "
                      "Files, consent and levels kept. Run the stages again from 1.", "ok")
            self.selected_file_id = 0
            self.refresh()

    def run_stage(self, n: int):
        out = self._api(api.post, f"/jobs/{self.job_id}/run/{int(n)}")
        if out is not None:
            self.running = True
            self.run = {"stage": int(n), "finished": None}
            self._say(f"Stage {n} started…", "info")

    # ---------- transcript ----------

    def select_file(self, v: str):
        self.selected_file_id = int(v)
        self._load_transcript()

    def compute_wer(self):
        cmp = self._api(api.post, f"/jobs/{self.job_id}/compare/{self.selected_file_id}",
                        {"reference": self.reference_text})
        if cmp:
            self.compare = {k: v for k, v in cmp.items() if k != "diff"}
            self.diff = cmp.get("diff", [])

    # ---------- artefacts ----------

    def start_maker_edit(self, art_id: int, current: str):
        self.maker_edit_id = int(art_id)
        self.maker_edit_text = current

    def save_maker(self):
        if self._api(api.patch, f"/artefacts/{self.maker_edit_id}", {"maker_statement": self.maker_edit_text}) is not None:
            self._say("Maker's statement saved. Re-run stage 4 to include it.", "ok")
            self.maker_edit_id = 0
            self.refresh()

    # ---------- sign-off ----------

    def review(self, theme_id: int, action: str):
        payload = {"actor_role": self.role, "action": action, "note": self.fix_note}
        if action == "fix":
            payload.update(label=self.fix_label, summary=self.fix_summary)
        out = self._api(api.patch, f"/themes/{int(theme_id)}", payload)
        if out is not None:
            self._say(f"Theme {theme_id}: {action} by {self.role}.", "ok")
            self.fix_id = 0
            self.fix_note = ""
            self.refresh()

    def start_fix(self, theme_id: int, label: str, summary: str):
        self.fix_id = int(theme_id)
        self.fix_label = label
        self.fix_summary = summary

    def cancel_fix(self):
        self.fix_id = 0

    def add_theme(self):
        ids = [int(x) for x in self.add_quote_ids.replace(",", " ").split() if x.strip().isdigit()]
        out = self._api(api.post, f"/jobs/{self.job_id}/themes",
                        {"label": self.add_label, "summary": self.add_summary, "quote_unit_ids": ids,
                         "from_level3": self.add_from_level3, "level": int(self.add_level)})
        if out is not None:
            self._say("Theme added by the community.", "ok")
            self.add_label = self.add_summary = self.add_quote_ids = ""
            self.add_from_level3 = False
            self.refresh()

    def set_people_count(self, theme_id: int, value: str):
        value = (value or "").strip()
        if not value:
            return
        if not value.isdigit():
            self._say("A count is a whole number.", "error")
            return
        if self._api(api.patch, f"/themes/{int(theme_id)}/people",
                     {"count": int(value), "actor_role": self.role}) is not None:
            self._say("Count saved.", "ok")
            self.refresh()

    # ---------- identify ----------

    def start_flag(self, flag_id: int):
        self.flag_edit_id = int(flag_id)
        self.flag_reason = ""

    def decide_flag(self, decision: str):
        out = self._api(api.post, f"/flags/{self.flag_edit_id}/decide",
                        {"decision": decision, "reason": self.flag_reason})
        if out is not None:
            self._say(f"Flag {self.flag_edit_id}: {decision}.", "ok")
            self.flag_edit_id = 0
            self.refresh()

    # ---------- reports ----------

    def approve(self, report_id: int):
        if self.role not in ("community", "analyst"):
            self._say("Only the community or the analyst approve a report.", "error")
            return
        if self._api(api.post, f"/reports/{int(report_id)}/approve", {"actor_role": self.role}) is not None:
            self._say(f"Approved by {self.role}.", "ok")
            self.refresh()

    def send_reportback(self):
        if self._api(api.post, f"/reports/{int(self.reportback['id'])}/send") is not None:
            self._say("Report-back marked as sent.", "ok")
            self.refresh()

    # ---------- chat with the data ----------

    def set_chat_input(self, v: str):
        self.chat_input = v

    def clear_chat(self):
        self.chat = []

    def load_chat(self):
        """On-load for the chat tab: take the job and role from the link it was opened with."""
        q = self.router.url.query_parameters
        if q.get("job", "").isdigit():
            self.job_id = int(q["job"])
        if q.get("role") in ROLES:
            self.role = q["role"]
        # A backend reload drops a question in flight; don't leave the box locked for good.
        self.chat_busy = False
        return AppState.load_all

    def submit_question(self, form_data: dict):
        self.chat_input = form_data.get("question", "")
        return AppState.send_question

    @rx.event(background=True)
    async def send_question(self):
        async with self:
            question = self.chat_input.strip()
            if not question or self.chat_busy:
                return
            history = [{"role": m["role"], "text": m["text"]} for m in self.chat]
            self.chat = [*self.chat, {"role": "user", "text": question, "sources": [], "has_sources": False}]
            self.chat_input = ""
            self.chat_busy = True
            job_id, role = self.job_id, self.role
        yield rx.scroll_to("chat-end")
        try:
            out = await asyncio.to_thread(api.ask, job_id, question, role, history)
            reply = {"role": "assistant", "text": out.get("answer", ""),
                     "sources": [{**s, "line": f"[{s['id']}] {s['file']} · {s['where']}"}
                                 for s in out.get("sources", [])]}
        except ApiError as e:
            reply = {"role": "error", "text": e.message, "sources": []}
        except Exception as e:  # noqa: BLE001
            reply = {"role": "error", "text": f"API not reachable: {e}", "sources": []}
        reply["has_sources"] = bool(reply["sources"])
        reply["sources_header"] = f"Sources ({len(reply['sources'])})"
        async with self:
            self.chat = [*self.chat, reply]
            self.chat_busy = False
        yield rx.scroll_to("chat-end")

    # ---------- concerns ----------

    def raise_concern(self):
        out = self._api(api.post, f"/jobs/{self.job_id}/concerns",
                        {"stage": int(self.concern_stage or 0), "text": self.concern_text})
        if out is not None:
            self._say("Thank you. A person will read this and sort it.", "ok")
            self.concern_text = ""
            self.concern_open = False
            self.refresh()

    def sort_concern(self, concern_id: int, category: str):
        if self._api(api.post, f"/concerns/{int(concern_id)}/sort", {"category": category}) is not None:
            self.refresh()
