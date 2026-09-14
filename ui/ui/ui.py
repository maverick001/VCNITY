"""VCNITY pipeline UI — one page per PRD §4 stage, a role switch, an audit
panel, and a 'raise a concern' button on every screen."""
from __future__ import annotations

from typing import Any

import reflex as rx

from .state import ROLES, AppState

# ---------------------------------------------------------------- layout


def level_badge(level) -> rx.Component:
    return rx.match(
        level.to(int),
        (1, rx.badge("Level 1 · Open", color_scheme="green")),
        (2, rx.badge("Level 2 · Sensitive", color_scheme="amber")),
        (3, rx.badge("Level 3 · Restricted — no AI", color_scheme="red")),
        rx.badge("?"),
    )


def status_badge(status) -> rx.Component:
    return rx.match(
        status.to(str),
        ("draft", rx.badge("draft", color_scheme="gray")),
        ("confirmed", rx.badge("confirmed by community", color_scheme="green")),
        ("fixed", rx.badge("fixed by community", color_scheme="green")),
        ("added", rx.badge("added by community", color_scheme="teal")),
        ("rejected", rx.badge("rejected by community", color_scheme="red")),
        ("cut", rx.badge("cut — identifiability", color_scheme="red")),
        ("unsupported", rx.badge("unsupported", color_scheme="orange")),
        rx.badge(status),
    )


def concern_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(rx.button("Raise a concern", variant="soft", color_scheme="tomato")),
        rx.dialog.content(
            rx.dialog.title("Raise a concern"),
            rx.dialog.description(
                "Say what happened, in your own words. You don't have to pick a category — a person sorts it."),
            rx.vstack(
                rx.text_area(placeholder="What happened?", value=AppState.concern_text,
                             on_change=AppState.set_concern_text, width="100%", rows="5"),
                rx.hstack(rx.text("Which stage?"),
                          rx.select([str(i) for i in range(10)], value=AppState.concern_stage,
                                    on_change=AppState.set_concern_stage)),
                rx.hstack(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.dialog.close(rx.button("Send", on_click=AppState.raise_concern)),
                    spacing="3"),
                spacing="3", width="100%"),
        ),
    )


def audit_panel() -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.cond(AppState.audit_ok,
                    rx.icon("shield-check", size=18, color="green"),
                    rx.icon("shield-alert", size=18, color="red")),
            rx.cond(AppState.audit_ok,
                    rx.badge("Level 3 → AI: 0 · hosted calls on L2+: 0", color_scheme="green", size="2"),
                    rx.badge("AUDIT BREACH", color_scheme="red", size="2")),
            rx.text("PRD §5: zero, no exceptions", size="1", color="gray"),
            rx.text(AppState.audit_total_text, size="1", color="gray"),
            spacing="3", align="center"),
        size="1", padding="12px 16px")


def stage_nav() -> rx.Component:
    def item(s):
        active = AppState.router.page.path == s["route"]
        return rx.link(
            rx.hstack(
                rx.cond(s["done"], rx.icon("circle-check", size=16, color="green"),
                        rx.icon("circle", size=16, color="gray")),
                rx.text(s["n"], " · ", s["name"], size="2"),
                spacing="2", align="center"),
            href=s["route"], underline="none", width="100%",
            padding="6px 10px", border_radius="6px",
            background_color=rx.cond(active, "var(--accent-4)", "transparent"),
            color=rx.cond(active, "var(--accent-12)", "inherit"),
            _hover={"background_color": rx.cond(active, "var(--accent-4)", "var(--gray-4)")})

    return rx.vstack(
        rx.heading("VCNITY", size="5"),
        rx.text("AI-assisted co-design analysis", size="1", color="gray"),
        rx.divider(),
        rx.foreach(AppState.stage_names, item),
        rx.divider(),
        rx.link(rx.text("Concerns", size="2"), href="/concerns", underline="none",
                width="100%", padding="6px 10px", border_radius="6px",
                _hover={"background_color": "var(--gray-4)"}),
        spacing="2", align="start", width="230px", min_width="230px", padding="20px",
        background_color="var(--gray-2)",
        border_right="1px solid var(--gray-5)", min_height="100vh")


def top_bar(title: str) -> rx.Component:
    return rx.hstack(
        rx.heading(title, size="6", weight="bold"),
        rx.spacer(),
        rx.hstack(rx.text("I am the", size="2", color="gray"),
                  rx.select(ROLES, value=AppState.role, on_change=AppState.set_role),
                  align="center"),
        rx.cond(AppState.jobs.length() > 1,
                rx.select(AppState.job_options, value=AppState.job_id.to(str), on_change=AppState.select_job),
                rx.fragment()),
        concern_dialog(),
        width="100%", align="center", spacing="4", wrap="wrap",
        padding_bottom="16px", border_bottom="1px solid var(--gray-5)")


def message_bar() -> rx.Component:
    return rx.cond(
        AppState.message != "",
        rx.match(
            AppState.message_kind,
            ("error", rx.callout(AppState.message, icon="triangle-alert", color_scheme="red", width="100%")),
            ("ok", rx.callout(AppState.message, icon="check", color_scheme="green", width="100%")),
            rx.callout(AppState.message, icon="info", width="100%"),
        ),
        rx.fragment())


def rerun_button(n: int, label: str = "Re-run this stage") -> rx.Component:
    return rx.button(rx.cond(AppState.running, "running…", label), on_click=AppState.run_stage(n),
                     disabled=AppState.running, variant="outline")


def page(title: str, *children) -> rx.Component:
    return rx.hstack(
        stage_nav(),
        rx.vstack(top_bar(title), audit_panel(), message_bar(), *children,
                  spacing="4", width="100%", padding="32px", max_width="1200px"),
        align="start", width="100%", spacing="0")


# ---------------------------------------------------------------- 0 intake

def file_row(f) -> rx.Component:
    return rx.table.row(
        rx.table.cell(f["filename"]),
        rx.table.cell(f["kind"]),
        rx.table.cell(
            rx.hstack(level_badge(f["level"]),
                      rx.select(["1", "2", "3"], value=f["level_text"].to(str),
                                on_change=lambda v: AppState.set_file_level(f["id"], v), size="1"),
                      align="center")),
        rx.table.cell(
            rx.cond(f["level"].to(int) == 1, rx.text("—", color="gray"),
                    rx.cond(f["confirmed"], rx.badge("confirmed by community", color_scheme="green"),
                            rx.button("Confirm level", size="1", on_click=AppState.confirm_file(f["id"]))))),
        rx.table.cell(rx.cond(f["consent_id"], rx.badge(f["consent_text"]),
                              rx.badge("NO CONSENT", color_scheme="red"))),
        _hover={"background_color": "var(--gray-3)"},
    )


UPLOAD_ACCEPT = {
    "audio/*": [".m4a", ".wav", ".mp3", ".mp4", ".aac", ".flac"],
    "image/*": [".jpg", ".jpeg", ".png", ".heic", ".webp"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "text/plain": [".txt", ".md"],
}


def upload_card() -> rx.Component:
    return rx.card(
        rx.heading("Upload a file", size="3"),
        rx.text("Audio, photos, PowerPoint, Word, or Excel. Every file needs a consent label and a sensitivity "
                "level before it can be used — set them below, then drop the file.", size="1", color="gray"),
        rx.upload.root(
            rx.vstack(
                rx.icon("upload", size=24),
                rx.text("Drag a file here, or click to choose one", size="2"),
                rx.foreach(rx.selected_files("facilitator_upload"),
                          lambda f: rx.badge(f, size="1", margin_top="4px")),
                align="center", spacing="1", padding="16px"),
            id="facilitator_upload",
            accept=UPLOAD_ACCEPT,
            max_files=5,
            border="1px dashed var(--gray-7)", border_radius="8px", width="100%"),
        rx.hstack(
            rx.vstack(rx.text("Sensitivity level", size="1", color="gray"),
                      rx.select(["1", "2", "3"], value=AppState.upload_level, on_change=AppState.set_upload_level),
                      spacing="1", align="start"),
            rx.vstack(rx.text("Consent label (required)", size="1", color="gray"),
                      rx.input(value=AppState.upload_consent_label, on_change=AppState.set_upload_consent_label,
                              placeholder="e.g. session-consent-2026-09-03", width="220px"),
                      spacing="1", align="start"),
            rx.vstack(rx.text("Consent scope (optional)", size="1", color="gray"),
                      rx.input(value=AppState.upload_consent_scope, on_change=AppState.set_upload_consent_scope,
                              placeholder="what was agreed to", width="220px"),
                      spacing="1", align="start"),
            spacing="4", wrap="wrap", align="end"),
        rx.cond(AppState.upload_error != "",
                rx.callout(AppState.upload_error, icon="triangle-alert", color_scheme="red", size="1"),
                rx.fragment()),
        rx.button(rx.cond(AppState.uploading, "Uploading…", "Upload"),
                  on_click=AppState.handle_upload(rx.upload_files(upload_id="facilitator_upload")),
                  disabled=AppState.uploading, size="2"),
        spacing="3", align="start", width="100%")


def intake_page() -> rx.Component:
    return page(
        "0 · Intake",
        rx.text("Every file gets a consent record and a sensitivity level. Nothing gets in without both. "
                "Levels only go up. Nothing above Level 1 goes near AI until a community reviewer confirms it.",
                color="gray"),
        rx.cond(AppState.has_waiting_level2,
                rx.callout(rx.text("Waiting for a community reviewer to confirm: ", AppState.waiting_level2_text),
                           icon="clock", color_scheme="amber", width="100%"),
                rx.fragment()),
        rx.cond(AppState.job_id == 0,
                rx.button("Create a job", on_click=AppState.create_job),
                rx.table.root(
                    rx.table.header(rx.table.row(
                        rx.table.column_header_cell("File"), rx.table.column_header_cell("Kind"),
                        rx.table.column_header_cell("Sensitivity"), rx.table.column_header_cell("Community check"),
                        rx.table.column_header_cell("Consent"))),
                    rx.table.body(rx.foreach(AppState.files, file_row)),
                    width="100%")),
        rx.cond((AppState.role == "facilitator") & (AppState.job_id != 0), upload_card(), rx.fragment()),
        rx.card(
            rx.heading("Brief", size="3"),
            rx.text(AppState.job_brief, white_space="pre-wrap", size="2"),
            width="100%"),
        rx.card(
            rx.heading("Community word list", size="3"),
            rx.text("Names, slang, local place words. One per line. Add @person after a name so Level 2 redaction removes it.",
                    size="1", color="gray"),
            rx.text_area(value=AppState.wordlist_text, on_change=AppState.set_wordlist_text, rows="8", width="100%"),
            rx.button("Save word list", on_click=AppState.save_wordlist, size="2"),
            width="100%"),
    )


# ---------------------------------------------------------------- 1 pipeline

def stage_card(s) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.cond(s["done"], rx.icon("circle-check", color="green"), rx.icon("circle", color="gray")),
            rx.vstack(rx.text(s["n"], " · ", s["name"], weight="bold"),
                      rx.link("open", href=s["route"], size="1"), spacing="0"),
            rx.spacer(),
            rx.button("Run", size="1", variant="outline", on_click=AppState.run_stage(s["n"]),
                      disabled=AppState.running),
            align="center", width="100%"),
        width="100%")


def pipeline_page() -> rx.Component:
    return page(
        "1 · Pipeline",
        rx.text("Every stage can be re-run live. AI stages refuse to run while a Level 2 file is unconfirmed, "
                "and stage 8 refuses while an identifiability flag is undecided.", color="gray"),
        rx.cond(AppState.running,
                rx.callout(rx.text("Stage ", AppState.run_stage_text, " is running — this page polls every 3 s."),
                           icon="loader", width="100%"),
                rx.fragment()),
        rx.foreach(AppState.stage_names, stage_card),
        rx.card(rx.heading("Job status", size="3"), rx.text(AppState.status_line, size="2"), width="100%"),
        rx.moment(interval=3000, on_change=AppState.poll, display="none"),
    )


# ---------------------------------------------------------------- 2 transcript

def seg_row(s) -> rx.Component:
    return rx.hstack(
        rx.text(s["start_text"], size="1", color="gray", width="52px", min_width="52px"),
        rx.badge(s["speaker_text"], size="1", color_scheme="gray"),
        rx.text(s["text"], size="2",
                background_color=rx.cond(s["unsure"], "var(--amber-3)", "transparent")),
        rx.cond(s["unsure"], rx.badge("not sure — needs a person", color_scheme="amber", size="1"), rx.fragment()),
        align="start", spacing="2", width="100%")


def diff_chunk(d) -> rx.Component:
    return rx.cond(
        d["kind"].to(str) == "same",
        rx.text(d["text"], " ", as_="span", size="2"),
        rx.text(rx.text(d["without"], as_="span", color="red", text_decoration="line-through"),
                " ", rx.text(d["with"], as_="span", color="green", weight="bold"), " ", as_="span", size="2"))


def transcript_page() -> rx.Component:
    return page(
        "2 · Transcription",
        rx.hstack(
            rx.text("Recording:"),
            rx.select(AppState.audio_options, value=AppState.selected_file_id.to(str), on_change=AppState.select_file),
            rerun_button(2), align="center"),
        rx.card(
            rx.heading("What the community word list changed", size="3"),
            rx.text(AppState.compare_line, size="2"),
            rx.text(AppState.compare_note, size="1", color="gray"),
            rx.box(rx.foreach(AppState.diff, diff_chunk), max_height="220px", overflow_y="auto",
                   padding="8px", border="1px solid var(--gray-5)", border_radius="6px"),
            rx.text("Paste a human-corrected transcript for this recording to get a real WER:", size="1", color="gray"),
            rx.text_area(value=AppState.reference_text, on_change=AppState.set_reference_text, rows="3", width="100%"),
            rx.hstack(rx.button("Compute WER", size="1", on_click=AppState.compute_wer),
                      rx.cond(AppState.has_reference_wer,
                              rx.text(AppState.reference_wer_line, size="2", weight="bold"), rx.fragment())),
            width="100%"),
        rx.hstack(
            rx.card(rx.heading("With word list (used downstream)", size="3"),
                    rx.vstack(rx.foreach(AppState.segments_with, seg_row), spacing="1", max_height="520px",
                              overflow_y="auto"), width="50%"),
            rx.card(rx.heading("Without word list", size="3"),
                    rx.vstack(rx.foreach(AppState.segments_without, seg_row), spacing="1", max_height="520px",
                              overflow_y="auto"), width="50%"),
            width="100%", align="start"),
    )


# ---------------------------------------------------------------- 3 artefacts

def artefact_card(a) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.image(src=a["image_url"], width="260px", height="auto", border_radius="6px"),
            rx.vstack(
                rx.hstack(rx.text(a["filename"], weight="bold", size="2"), level_badge(a["level"]),
                          rx.cond(a["illegible_count"].to(int) > 0,
                                  rx.badge(a["illegible_text"], color_scheme="amber"), rx.fragment()),
                          wrap="wrap"),
                rx.text("What is written (verbatim, spelling kept):", size="1", color="gray"),
                rx.text(a["verbatim_text"], white_space="pre-wrap", size="2", font_family="monospace"),
                rx.text("What is in the frame:", size="1", color="gray"),
                rx.text(a["description"], size="2"),
                rx.text("What the maker said it means (a person fills this in — AI never does):", size="1", color="gray"),
                rx.cond(AppState.maker_edit_id == a["id"].to(int),
                        rx.vstack(rx.text_area(value=AppState.maker_edit_text, on_change=AppState.set_maker_edit_text,
                                               rows="3", width="100%"),
                                  rx.button("Save", size="1", on_click=AppState.save_maker), width="100%"),
                        rx.hstack(rx.text(a["maker_text"], size="2"),
                                  rx.button("Edit", size="1", variant="soft",
                                            on_click=AppState.start_maker_edit(a["id"], a["maker_statement"])))),
                align="start", spacing="2", width="100%"),
            align="start", spacing="4", width="100%"),
        width="100%")


def artefacts_page() -> rx.Component:
    return page(
        "3 · Things people made",
        rx.text("The model reads what is physically written and describes what is in the frame. It is told never to "
                "say what anything means. Meaning comes from what the maker said — the last field on each card.",
                color="gray"),
        rerun_button(3),
        rx.foreach(AppState.artefacts, artefact_card),
    )


# ---------------------------------------------------------------- 4/5 themes

def quote_row(q) -> rx.Component:
    return rx.hstack(rx.badge(q["id_text"], size="1"), rx.badge(q["speaker"], size="1", color_scheme="gray"),
                     rx.text(q["text"], size="2"), align="start", spacing="2")


def theme_card(t, actions: bool = False) -> rx.Component:
    body = [
        rx.hstack(rx.heading(t["label"], size="4"), status_badge(t["status"]), level_badge(t["level"]),
                  rx.badge(t["people_text"], color_scheme="gray"), align="center", wrap="wrap"),
        rx.text(t["summary"], size="2"),
        rx.accordion.root(rx.accordion.item(
            header=rx.text(t["quotes_header"]),
            content=rx.vstack(rx.foreach(t["quotes"].to(list[dict[str, Any]]), quote_row), spacing="1")),
            collapsible=True, variant="ghost", width="100%"),
        rx.cond(t["has_note"], rx.text(t["review_note"], size="1", color="gray", white_space="pre-wrap"),
                rx.fragment()),
    ]
    if actions:
        body.append(signoff_actions(t))
    return rx.card(rx.vstack(*body, spacing="2", align="start", width="100%"), width="100%")


def themes_page() -> rx.Component:
    return page(
        "4 · Draft themes  ·  5 · Evidence check",
        rx.text("Quotes come from the clustering, not from the model — it only labels each group from its quotes. "
                "The evidence check hides any theme whose summary says more than its quotes do.", color="gray"),
        rx.hstack(rerun_button(4, "Re-run 4 · draft themes"), rerun_button(5, "Re-run 5 · evidence check")),
        rx.cond(AppState.unsupported_count > 0,
                rx.callout(rx.text(AppState.unsupported_count,
                                   " theme(s) failed the evidence check and are hidden from reviewers. Analyst view below."),
                           icon="shield-alert", color_scheme="orange", width="100%"),
                rx.fragment()),
        rx.foreach(AppState.themes, lambda t: theme_card(t)),
        rx.cond(AppState.role == "analyst",
                rx.card(rx.heading("Thrown out by the evidence check", size="3"),
                        rx.foreach(AppState.unsupported, lambda u: rx.text(u["line"], size="2")),
                        width="100%"),
                rx.fragment()),
    )


# ---------------------------------------------------------------- 6 sign-off

def signoff_actions(t) -> rx.Component:
    community = rx.cond(
        AppState.fix_id == t["id"].to(int),
        rx.vstack(
            rx.input(value=AppState.fix_label, on_change=AppState.set_fix_label, placeholder="Label", width="100%"),
            rx.text_area(value=AppState.fix_summary, on_change=AppState.set_fix_summary, placeholder="Summary",
                         rows="3", width="100%"),
            rx.input(value=AppState.fix_note, on_change=AppState.set_fix_note, placeholder="Why (optional)",
                     width="100%"),
            rx.hstack(rx.button("Save fix", size="1", on_click=AppState.review(t["id"], "fix")),
                      rx.button("Cancel", size="1", variant="soft", on_click=AppState.cancel_fix)),
            width="100%"),
        rx.hstack(
            rx.button("Confirm", size="1", color_scheme="green", on_click=AppState.review(t["id"], "confirm")),
            rx.button("Fix", size="1", color_scheme="amber",
                      on_click=AppState.start_fix(t["id"], t["label"], t["summary"])),
            rx.button("Reject", size="1", color_scheme="red", on_click=AppState.review(t["id"], "reject")),
            spacing="2"))
    analyst = rx.cond(
        t["decided_by"].to(str) == "community",
        rx.badge("Locked — the community decided. Try it: the API answers 409.", color_scheme="gray"),
        rx.hstack(rx.input(value=AppState.fix_note, on_change=AppState.set_fix_note,
                           placeholder="Analyst note (no status change)", width="300px"),
                  rx.button("Add note", size="1", variant="soft", on_click=AppState.review(t["id"], "note")),
                  rx.button("Try to confirm (will be refused)", size="1", variant="outline", color_scheme="red",
                            on_click=AppState.review(t["id"], "confirm")), wrap="wrap"))
    return rx.match(AppState.role, ("community", community), ("analyst", analyst),
                    rx.text("Switch role to community or analyst to act.", size="1", color="gray"))


def signoff_page() -> rx.Component:
    return page(
        "6 · Community sign-off",
        rx.callout("When the community and the analyst disagree about what material means, the community decides. "
                   "That isn't negotiable.", icon="scale", width="100%"),
        rx.foreach(AppState.themes, lambda t: theme_card(t, actions=True)),
        rx.cond(AppState.role == "community",
                rx.card(rx.heading("Add a theme we missed", size="3"),
                        rx.input(value=AppState.add_label, on_change=AppState.set_add_label, placeholder="Label", width="100%"),
                        rx.text_area(value=AppState.add_summary, on_change=AppState.set_add_summary,
                                     placeholder="What it says", rows="2", width="100%"),
                        rx.input(value=AppState.add_quote_ids, on_change=AppState.set_add_quote_ids,
                                 placeholder="Quote ids behind it, e.g. 12 15 (from the list below)", width="100%"),
                        rx.button("Add theme", size="2", on_click=AppState.add_theme),
                        rx.accordion.root(rx.accordion.item(
                            header=rx.text("All quotable material"),
                            content=rx.vstack(rx.foreach(AppState.units, lambda u: rx.text(u["line"], size="1")),
                                              spacing="1", max_height="300px", overflow_y="auto")),
                            collapsible=True, variant="ghost", width="100%"),
                        width="100%"),
                rx.fragment()),
    )


# ---------------------------------------------------------------- 7 identify

def flag_row(f) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(rx.match(f["kind"].to(str), ("pii", rx.badge("pii", color_scheme="red")),
                               rx.badge("small_n", color_scheme="amber")),
                      rx.text(f["theme_label"], weight="bold"), align="center"),
            rx.text(f["detail"], size="2"),
            rx.cond(f["decision"],
                    rx.text(f["decision_text"], size="2", color="green"),
                    rx.cond(AppState.role == "analyst",
                            rx.cond(AppState.flag_edit_id == f["id"].to(int),
                                    rx.vstack(rx.input(value=AppState.flag_reason, on_change=AppState.set_flag_reason,
                                                       placeholder="Write down why (required)", width="100%"),
                                              rx.hstack(rx.button("Keep", size="1", color_scheme="green",
                                                                  on_click=AppState.decide_flag("keep")),
                                                        rx.button("Cut", size="1", color_scheme="red",
                                                                  on_click=AppState.decide_flag("cut"))),
                                              width="100%"),
                                    rx.button("Decide", size="1", on_click=AppState.start_flag(f["id"]))),
                            rx.text("Waiting for the analyst.", size="1", color="gray"))),
            align="start", spacing="2", width="100%"),
        width="100%")


def identify_page() -> rx.Component:
    return page(
        "7 · Could anyone be identified?",
        rx.text("Themes from very few people, and anything that gives someone away. The analyst decides what to cut "
                "and writes down why — stage 8 will not run until every flag has a decision.", color="gray"),
        rerun_button(7, "Re-run flags"),
        rx.cond(AppState.flags.length() == 0, rx.text("No flags yet.", color="gray"), rx.fragment()),
        rx.foreach(AppState.flags, flag_row),
    )


# ---------------------------------------------------------------- 8/9 reports

def approvals(r) -> rx.Component:
    return rx.hstack(
        rx.cond(r["approved_community"], rx.badge("community approved", color_scheme="green"),
                rx.badge("community: not yet", color_scheme="gray")),
        rx.cond(r["approved_analyst"], rx.badge("analyst approved", color_scheme="green"),
                rx.badge("analyst: not yet", color_scheme="gray")),
        rx.button(rx.text("Approve as ", AppState.role), size="1", on_click=AppState.approve(r["id"]),
                  disabled=(AppState.role != "community") & (AppState.role != "analyst")),
        align="center", spacing="2", wrap="wrap")


def report_page() -> rx.Component:
    return page(
        "8 · Report",
        rx.text("Shaped like the client's own engagement reports: background, how we engaged, a theme table with "
                "'N of M participants', findings. Only signed-off themes appear. Both approvals before it leaves.",
                color="gray"),
        rerun_button(8, "Re-draft report"),
        rx.cond(AppState.has_client_report,
                rx.vstack(
                    approvals(AppState.client_report),
                    rx.cond(AppState.can_export,
                            rx.link(rx.button("Export .docx"), href=AppState.export_url, is_external=True),
                            rx.button("Export .docx (needs both approvals)", disabled=True)),
                    rx.card(rx.markdown(AppState.client_report["markdown"].to(str)), width="100%"),
                    width="100%", align="start"),
                rx.text("Not drafted yet.", color="gray")),
    )


def reportback_page() -> rx.Component:
    return page(
        "9 · Report back",
        rx.text("A plain-language version for the people who took part. Same two approvals; 'send' only marks it "
                "sent in this prototype.", color="gray"),
        rerun_button(9, "Re-draft report-back"),
        rx.cond(AppState.has_reportback,
                rx.vstack(
                    approvals(AppState.reportback),
                    rx.cond(AppState.reportback["sent"], rx.badge("sent", color_scheme="green"),
                            rx.button("Send to participants", on_click=AppState.send_reportback,
                                      disabled=~AppState.can_send)),
                    rx.card(rx.markdown(AppState.reportback["markdown"].to(str)), width="100%"),
                    width="100%", align="start"),
                rx.text("Not drafted yet.", color="gray")),
    )


# ---------------------------------------------------------------- concerns

def concern_row(c) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(rx.badge(c["stage_text"]), rx.badge(c["status"], color_scheme="gray"),
                      rx.cond(c["category"], rx.badge(c["category"], color_scheme="tomato"), rx.fragment()),
                      align="center"),
            rx.text(c["text"], size="2"),
            rx.cond(c["routed_text"].to(str) != "",
                    rx.text(c["routed_text"], size="1"),
                    rx.cond(AppState.role == "analyst",
                            rx.hstack(rx.text("Sort as:", size="1"),
                                      rx.button("harm", size="1", variant="soft", on_click=AppState.sort_concern(c["id"], "harm")),
                                      rx.button("misuse", size="1", variant="soft", on_click=AppState.sort_concern(c["id"], "misuse")),
                                      rx.button("conduct", size="1", variant="soft", on_click=AppState.sort_concern(c["id"], "conduct")),
                                      rx.button("ai_error", size="1", variant="soft", on_click=AppState.sort_concern(c["id"], "ai_error")),
                                      wrap="wrap"),
                            rx.text("A person will sort this.", size="1", color="gray"))),
            align="start", spacing="2"),
        width="100%")


def concerns_page() -> rx.Component:
    return page(
        "Concerns",
        rx.text("One obvious way to raise something, from any stage, in the person's own words. They describe what "
                "happened; a person sorts it. Harm → a named person, same day (PRD A13 — still UNSET).", color="gray"),
        rx.foreach(AppState.concerns, concern_row),
    )


# ---------------------------------------------------------------- app

app = rx.App(theme=rx.theme(accent_color="teal", radius="medium"))
for route, component in [("/", intake_page), ("/pipeline", pipeline_page), ("/transcript", transcript_page),
                         ("/artefacts", artefacts_page), ("/themes", themes_page), ("/signoff", signoff_page),
                         ("/identify", identify_page), ("/report", report_page), ("/reportback", reportback_page),
                         ("/concerns", concerns_page)]:
    app.add_page(component, route=route, on_load=AppState.load_all, title="VCNITY pipeline")
