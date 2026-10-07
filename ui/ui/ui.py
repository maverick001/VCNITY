"""VCNITY pipeline UI — a sign-in page, one page per PRD §4 stage, an audit
panel, and a 'Chat with Data' page, opened in its own tab, for the facilitator and analyst (PRD A19)."""
from __future__ import annotations

from typing import Any

import reflex as rx

from .community import community_page
from .state import STAGE_INFO, AppState

# ---------------------------------------------------------------- layout

# Radix's blue scale, so it turns dark blue by itself in dark mode.
PAGE_BG = "var(--blue-3)"


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


def origin_badge(t) -> rx.Component:
    return rx.fragment(
        rx.cond(t["agreed_upfront"], rx.badge("agreed at intake", color_scheme="teal"), rx.fragment()),
        rx.cond(t["from_level3"], rx.badge("from Level 3 material — no quotes", color_scheme="red"), rx.fragment()))


def chat_source(src) -> rx.Component:
    return rx.vstack(
        rx.text(src["line"], size="1", weight="bold", color="var(--accent-11)", word_break="break-word"),
        rx.text(src["text"], size="2", color="gray"),
        spacing="1", align="start", width="100%",
        padding="8px 10px", border_left="2px solid var(--accent-6)", background_color="var(--gray-2)")


def chat_message(m) -> rx.Component:
    bubble = rx.box(
        # The model writes a little markdown (bold, lists); show it as formatting, not asterisks.
        rx.cond(m["role"] == "assistant",
                rx.markdown(m["text"]),
                rx.text(m["text"], size="3", white_space="pre-wrap")),
        rx.cond(m["has_sources"],
                rx.accordion.root(rx.accordion.item(
                    header=rx.text(m["sources_header"], size="2"),
                    content=rx.vstack(rx.foreach(m["sources"].to(list[dict[str, Any]]), chat_source),
                                      spacing="2", align="start", width="100%")),
                    collapsible=True, variant="ghost", width="100%", margin_top="8px"),
                rx.fragment()),
        padding="12px 16px", border_radius="12px",
        max_width=rx.cond(m["role"] == "user", "75%", "100%"),
        background_color=rx.match(m["role"], ("user", "var(--accent-4)"), ("error", "var(--red-3)"),
                                  "var(--color-panel-solid)"))
    return rx.hstack(bubble, width="100%",
                     justify=rx.cond(m["role"] == "user", "end", "start"))


def chat_button() -> rx.Component:
    # Opens the chat in its own browser tab. Solid violet: the only filled button in the top bar,
    # and a colour nothing else in the app uses.
    return rx.link(rx.button(rx.icon("messages-square", size=16), "Chat with Data",
                             rx.icon("external-link", size=14),
                             variant="solid", color_scheme="violet", size="2", high_contrast=False,
                             box_shadow="0 0 0 3px var(--violet-a4)", cursor="pointer"),
                   href=AppState.chat_url, is_external=True)


def chat_page() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.hstack(
                rx.icon("messages-square", size=22, color="var(--violet-11)"),
                rx.heading("Chat with Data", size="5"),
                rx.badge(AppState.job["name"].to(str), color_scheme="gray", size="2"),
                rx.badge(rx.text("as ", AppState.role), color_scheme="violet", size="2"),
                rx.spacer(),
                rx.button(rx.icon("eraser", size=14), "Clear", size="2", variant="soft", color_scheme="gray",
                          on_click=AppState.clear_chat, disabled=AppState.chat.length() == 0),
                align="center", width="100%", spacing="3", wrap="wrap"),
            rx.text("Answers come only from this job's material below Level 3, with sources. It won't say "
                    "what anything means — that's the community's call at sign-off. Names in Level 2 "
                    "material may appear as made-up stand-ins. Nothing is kept after you reload the page.",
                    size="2", color="gray"),
            width="100%", max_width="860px", spacing="2",
            padding="20px 24px 16px", margin="0 auto"),
        rx.box(
            rx.vstack(
                rx.cond(~AppState.can_ask,
                        rx.callout("Only the facilitator or the analyst can ask questions.", icon="lock",
                                   color_scheme="amber", width="100%"),
                        rx.fragment()),
                rx.cond((AppState.message_kind == "error") & (AppState.message != ""),
                        rx.callout(AppState.message, icon="triangle-alert", color_scheme="red", width="100%"),
                        rx.fragment()),
                rx.cond(AppState.chat.length() == 0,
                        rx.center(rx.vstack(
                            rx.icon("message-circle-question", size=36, color="var(--gray-8)"),
                            rx.text("Ask about a topic, not a meaning. For example:", size="2", color="gray"),
                            rx.text("“What did people say about public transport?”", size="2"),
                            rx.text("“Where do people mention feeling unsafe?”", size="2"),
                            align="center", spacing="2"), width="100%", padding_top="15vh"),
                        rx.fragment()),
                rx.foreach(AppState.chat, chat_message),
                rx.cond(AppState.chat_busy,
                        rx.hstack(rx.spinner(size="2"),
                                  rx.text("Reading the material… this can take a minute", size="2",
                                          color="gray"), align="center"),
                        rx.fragment()),
                rx.box(id="chat-end"),
                spacing="4", width="100%", max_width="860px", margin="0 auto", padding="8px 24px 24px"),
            flex="1", width="100%", overflow_y="auto",
            border_top="1px solid var(--gray-5)"),
        rx.box(
            rx.form(
                rx.hstack(
                    # A plain textarea, left uncontrolled: the text is read from the submitted form rather than
                    # a debounced on_change. Enter sends and Shift+Enter adds a line. Written out here because
                    # Reflex 0.9's enter_key_submit calls a helper it never imports into memoized components.
                    # Enter while an input method is composing (e.g. Chinese) picks a character, not send.
                    rx.el.textarea(name="question", rows=2,
                                   custom_attrs={"on_key_down": rx.Var(
                                       "(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing)"
                                       " { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }")},
                                   placeholder="Ask about the material…  (Enter to send, Shift+Enter for a new line)",
                                   disabled=AppState.chat_busy | ~AppState.can_ask,
                                   width="100%", padding="10px 12px", resize="none", font_size="var(--font-size-3)",
                                   font_family="inherit", color="var(--gray-12)", background_color="var(--gray-a2)",
                                   border="1px solid var(--gray-a7)", border_radius="var(--radius-3)",
                                   _focus={"outline": "2px solid var(--accent-8)", "outline_offset": "-1px"}),
                    rx.button(rx.icon("send", size=18), type="submit", size="4",
                              disabled=AppState.chat_busy | ~AppState.can_ask),
                    width="100%", align="end", spacing="3"),
                on_submit=AppState.submit_question, reset_on_submit=True,
                width="100%", max_width="860px", margin="0 auto", padding="16px 24px 20px"),
            width="100%", border_top="1px solid var(--gray-5)", background_color="var(--color-panel-solid)"),
        height="100vh", width="100%", spacing="0", background_color=PAGE_BG)


# The sidebar and the page are built on the same rows so their lines and text sit level with each other:
# the divider under the logo block meets the line under the page title, "Agent Workflow" meets the audit bar,
# and the first step meets the "AI does" cards. The page spaces its blocks 16px apart (spacing="4"); the sidebar
# spaces its rows 4px apart (spacing="1"), so it adds 12px where the page has 16.
BAR_H = "64px"    # logo block (sidebar) and title bar (page), each ending in a 1px line
AUDIT_H = "52px"  # the audit bar (page) and the Agent Workflow row (sidebar)


def audit_panel(show_prd_note: bool = True) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.cond(AppState.audit_ok,
                    rx.icon("shield-check", size=18, color="green"),
                    rx.icon("shield-alert", size=18, color="red")),
            rx.cond(AppState.audit_ok,
                    rx.badge("Level 3 → AI: 0 · hosted calls on L2+: 0", color_scheme="green", size="2"),
                    rx.badge("AUDIT BREACH", color_scheme="red", size="2")),
            rx.text("PRD §5: zero, no exceptions", size="1", color="gray") if show_prd_note else rx.fragment(),
            rx.text(AppState.audit_total_text, size="1", color="gray"),
            spacing="3", align="center"),
        size="1", padding="0 16px", height=AUDIT_H, display="flex", align_items="center")


def _nav_style(active):
    return dict(width="100%", padding="7px 10px", border_radius="8px",
                background_color=rx.cond(active, "var(--accent-5)", "transparent"),
                color=rx.cond(active, "var(--accent-12)", "inherit"),
                font_weight=rx.cond(active, "700", "normal"),
                box_shadow=rx.cond(active, "inset 4px 0 0 var(--accent-9), 0 0 0 1px var(--accent-7)", "none"),
                transition="background-color 120ms",
                _hover={"background_color": rx.cond(active, "var(--accent-6)", "var(--gray-4)")})


def stage_nav() -> rx.Component:
    def row(s):
        return rx.hstack(
            rx.cond(s["done"], rx.icon("circle-check", size=16, color="var(--green-9)", flex_shrink="0"),
                    rx.icon("circle", size=16, color="var(--gray-8)", flex_shrink="0")),
            rx.text(s["n"], " · ", s["name"], size="2", white_space="nowrap", overflow="hidden",
                    text_overflow="ellipsis", min_width="0", title=s["name"]),
            rx.spacer(),
            rx.cond(s["is_waiting"],
                    rx.tooltip(rx.icon("user-round-pen", size=15, color="var(--amber-10)", flex_shrink="0"),
                               content="Pending human input: " + s["waiting"].to(str)),
                    rx.fragment()),
            spacing="2", align="center", width="100%")

    def item(s):
        active = AppState.current_path == s["route"]
        return rx.cond(
            s["has_route"],
            rx.link(row(s), href=s["route"], underline="none", **_nav_style(active)),
            rx.tooltip(rx.box(row(s), width="100%", padding="6px 10px", color="var(--gray-10)"),
                       content="Runs in the background — no screen, nothing for a person to do"))

    def top_link(logo: rx.Component, label: str, href: str, active, **extra) -> rx.Component:
        """Agent Workflow and Model Configuration: a 32px logo at the VCNITY logo's left edge and the text 12px
        after it, as in the logo block above. The row reaches 10px further left (its padding) so the highlight
        still wraps the logo."""
        return rx.link(rx.hstack(logo, rx.heading(label, size="3", line_height="1", white_space="nowrap"),
                                 spacing="3", align="center", height="100%"),
                       href=href, underline="none",
                       **{**_nav_style(active), "padding": "0 10px", "width": "calc(100% + 10px)"},
                       height=AUDIT_H, flex_shrink="0", margin_left="-10px", **extra)

    overview_active = AppState.current_path == "/pipeline"
    return rx.vstack(
        rx.hstack(
            rx.center(rx.icon("waypoints", size=18, color="white"), background_color="var(--accent-9)",
                      border_radius="8px", width="32px", height="32px", flex_shrink="0"),
            rx.vstack(rx.heading("VCNITY", size="4", line_height="1"),
                      rx.text("AI-assisted co-design analysis", size="1", color="gray"),
                      spacing="1", align="start"),
            spacing="3", align="center", width="100%", height=BAR_H, flex_shrink="0",
            border_bottom="1px solid var(--blue-6)"),
        # The overview runs every stage: analyst work. The facilitator keeps an empty slot so their steps sit
        # at the same height as the analyst's.
        rx.cond(AppState.role == "facilitator",
                rx.box(height=AUDIT_H, width="100%", flex_shrink="0", margin_top="12px"),
                top_link(rx.image(src="/agent.png", alt="", height="32px", width="32px", flex_shrink="0"),
                         "Agent Workflow", "/pipeline", overview_active, margin_top="12px")),
        rx.box(height="8px", width="100%", flex_shrink="0"),  # the column's own 4px gaps make this 16
        rx.foreach(AppState.stage_names, item),
        # Model names are the analyst's business; the facilitator never sees this link or the page.
        rx.cond(AppState.role == "analyst",
                rx.vstack(rx.divider(margin_y="8px"),
                          top_link(rx.center(rx.icon("cpu", size=18, color="white"), background_color="var(--accent-9)",
                                             border_radius="8px", width="32px", height="32px", flex_shrink="0"),
                                   "Model Configuration", "/models", AppState.current_path == "/models"),
                          spacing="1", width="100%"),
                rx.fragment()),
        rx.spacer(),
        rx.hstack(rx.icon("user-round-pen", size=14, color="var(--amber-10)"),
                  rx.text("pending human input", size="1", color="gray"), spacing="2", align="center"),
        spacing="1", align="start", width="300px", min_width="300px", flex_shrink="0", padding="32px 20px 20px",
        background_color="var(--color-panel-solid)", border_right="1px solid var(--blue-5)", min_height="100vh",
        position="sticky", top="0")


def stage_header(*ns: int) -> rx.Component:
    """The PRD's pipeline row for this page: what the AI does, what a person does."""
    def column(icon: str, title: str, idx: int) -> rx.Component:
        lines = []
        for n in ns:
            text = STAGE_INFO[n][idx]
            lines.append(rx.text(rx.text(f"{n} · ", as_="span", weight="bold") if len(ns) > 1 else "",
                                 text, size="2", color="var(--gray-9)" if text == "—" else "inherit"))
        return rx.vstack(rx.hstack(rx.icon(icon, size=16), rx.text(title, size="2", weight="bold"),
                                   spacing="2", align="center"),
                         *lines, spacing="1", align="start", width="100%")

    return rx.cond(
        AppState.role == "facilitator", rx.fragment(),  # the facilitator's pages don't carry this row
        rx.grid(
            rx.card(column("bot", "AI does", 0), variant="surface"),
            rx.card(column("user-round", "A person does", 1), variant="surface"),
            columns=rx.breakpoints(initial="1", sm="2"), spacing="3", width="100%"))


def user_chip() -> rx.Component:
    return rx.hstack(
        rx.icon("circle-user-round", size=18, color="var(--gray-10)"),
        rx.text(AppState.username, size="2", weight="medium"),
        rx.badge(AppState.role, color_scheme="gray"),
        rx.button(rx.icon("log-out", size=14), "Sign out", size="1", variant="ghost", color_scheme="gray",
                  on_click=AppState.logout),
        align="center", spacing="2")


def top_bar(title: str, show_jobs: bool = True, beside_title: rx.Component | None = None) -> rx.Component:
    return rx.hstack(
        rx.heading(title, size="6", weight="bold"),
        beside_title if beside_title is not None else rx.fragment(),
        rx.spacer(),
        user_chip(),
        rx.cond(AppState.jobs.length() > 1,
                rx.select(AppState.job_options, value=AppState.job_id.to(str), on_change=AppState.select_job),
                rx.fragment()) if show_jobs else rx.fragment(),
        rx.cond(AppState.can_ask, chat_button(), rx.fragment()),
        width="100%", align="center", spacing="4", wrap="wrap",
        min_height=BAR_H, border_bottom="1px solid var(--blue-6)")


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
    # Only the analyst runs stages (PRD §3: the facilitator does no analyst work).
    return rx.cond(AppState.role == "analyst",
                   rx.button(rx.cond(AppState.running, "running…", label), on_click=AppState.run_stage(n),
                             disabled=AppState.running, variant="outline"),
                   rx.fragment())


def page(title: str, *children, beside_title: rx.Component | None = None,
         show_prd_note: bool = True) -> rx.Component:
    return rx.hstack(
        stage_nav(),
        rx.vstack(top_bar(title, beside_title=beside_title),
                  rx.cond(AppState.role == "facilitator", rx.fragment(), audit_panel(show_prd_note)),
                  message_bar(), *children,
                  spacing="4", width="100%", padding="32px", max_width="1200px"),
        align="start", width="100%", spacing="0", min_height="100vh",
        background_color="var(--color-panel-solid)")  # same white as the sidebar


# ---------------------------------------------------------------- 0 intake

def file_row(f) -> rx.Component:
    return rx.table.row(
        rx.table.cell(f["filename"]),
        rx.table.cell(f["file_id_text"]),
        rx.table.cell(
            rx.hstack(level_badge(f["level"]),
                      rx.cond((AppState.role == "facilitator") | (AppState.role == "analyst"),
                              rx.select(f["level_options"].to(list[str]), value=f["level_text"].to(str),
                                        on_change=lambda v: AppState.set_file_level(f["id"], v), size="1"),
                              rx.fragment()),
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


def attendance_card() -> rx.Component:
    return rx.card(
        rx.heading("Who came", size="3"),
        rx.text("How many people came to each session. The total is the 'of M' in the report's "
                "'N of M participants' (PRD A6). The facilitator enters it.", size="1", color="gray"),
        rx.foreach(AppState.attendance, lambda r: rx.hstack(
            rx.text(r["line"], size="2"),
            rx.cond(AppState.role == "facilitator",
                    rx.button("Remove", size="1", variant="soft", on_click=AppState.remove_attendance(r["i"])),
                    rx.fragment()),
            align="center")),
        rx.text(AppState.attendance_total_text, size="2", weight="bold"),
        rx.cond(AppState.role == "facilitator",
                rx.hstack(
                    rx.input(value=AppState.att_session, on_change=AppState.set_att_session,
                             placeholder="Session, e.g. Tue 3 Sep, Goodna", width="240px"),
                    rx.input(value=AppState.att_count, on_change=AppState.set_att_count, placeholder="People",
                             width="90px"),
                    rx.button("Add", size="2", on_click=AppState.add_attendance), align="center"),
                rx.fragment()),
        spacing="2", width="100%")


def agreed_card() -> rx.Component:
    return rx.card(
        rx.heading("Themes agreed with the community", size="3"),
        rx.text("Agreed before anything is sorted (PRD A17). Stage 4 sorts every bit of material into these, and "
                "suggests new themes for anything that doesn't fit.", size="1", color="gray"),
        rx.foreach(AppState.agreed_themes, lambda t: rx.hstack(
            rx.text(t["label"], weight="bold", size="2"), rx.text(t["summary"], size="2", color="gray"),
            status_badge(t["status"]), align="center", wrap="wrap")),
        rx.cond(AppState.role == "community",
                rx.vstack(
                    rx.input(value=AppState.agreed_label, on_change=AppState.set_agreed_label, placeholder="Theme",
                             width="100%"),
                    rx.text_area(value=AppState.agreed_summary, on_change=AppState.set_agreed_summary,
                                 placeholder="What it covers, in the community's words", rows="2", width="100%"),
                    rx.hstack(rx.text("Level of the wording", size="1", color="gray"),
                              rx.select(["1", "2"], value=AppState.agreed_level, on_change=AppState.set_agreed_level,
                                        size="1"),
                              rx.button("Agree theme", size="2", on_click=AppState.add_agreed_theme), align="center"),
                    width="100%"),
                rx.text("A community reviewer adds these on their own page.", size="1", color="gray")),
        spacing="2", width="100%")


def levels_card() -> rx.Component:
    def row(level: int, whats_in: str, allowed: str) -> rx.Component:
        return rx.table.row(rx.table.cell(level_badge(rx.Var.create(level))),
                            rx.table.cell(whats_in, white_space="normal"),
                            rx.table.cell(allowed, white_space="normal"))

    return rx.card(
        rx.heading("Sensitivity levels", size="3"),
        rx.text("Set on upload. The facilitator can change a level up or down, the analyst can only raise one, and the "
                "community must confirm it again after any change. Not sure? Go up a level. Nothing above Level 1 goes near AI until a "
                "community reviewer confirms it.",
                size="1", color="gray"),
        rx.table.root(
            rx.table.header(rx.table.row(rx.table.column_header_cell("Level", width="190px"),
                                         rx.table.column_header_cell("What's in it", width="38%"),
                                         rx.table.column_header_cell("What's allowed"))),
            rx.table.body(
                row(1, "General comments about places, services, surroundings", "AI can analyse it"),
                row(2, "Personal experience, health and wellbeing, anything tied to a known group",
                    "AI only after real names are swapped for made-up ones, and a person checks. Transcription "
                    "and photo description are the exception"),
                row(3, "First Nations cultural knowledge, disclosures of harm, anything the community restricts",
                    "No AI at all. People transcribe it by hand. A theme the community writes from it can reach "
                    "the client, never the material")),
            size="1", width="100%", style={"table_layout": "fixed"}),
        width="100%")


def wordlist_card() -> rx.Component:
    return rx.card(
        rx.heading("Community word list", size="3"),
        rx.text("Names, slang, local place words — one per line. Add @person after a name so Level 2 material gets "
                "a made-up name for it. Re-run this stage after saving.", size="1", color="gray"),
        rx.text_area(value=AppState.wordlist_text, on_change=AppState.set_wordlist_text, rows="6", width="100%"),
        rx.button("Save word list", on_click=AppState.save_wordlist, size="2"),
        width="100%")


def intake_files() -> rx.Component:
    return rx.cond(AppState.job_id == 0,
                   rx.button("Create a job", on_click=AppState.create_job),
                   rx.table.root(
                       rx.table.header(rx.table.row(
                           rx.table.column_header_cell("File"), rx.table.column_header_cell("File_ID"),
                           rx.table.column_header_cell("Sensitivity"), rx.table.column_header_cell("Community check"),
                           rx.table.column_header_cell("Consent"))),
                       rx.table.body(rx.foreach(AppState.files, file_row)),
                       width="100%"))


def intake_tools() -> list[rx.Component]:
    """Upload, the levels note, and who came / agreed themes: everything on the page except the files list."""
    return [
        rx.cond((AppState.role == "facilitator") & (AppState.job_id != 0), upload_card(), rx.fragment()),
        levels_card(),
        rx.cond(AppState.job_id != 0,
                rx.grid(attendance_card(), agreed_card(), columns=rx.breakpoints(initial="1", md="2"), spacing="4",
                        width="100%"),
                rx.fragment()),
    ]


def intake_page() -> rx.Component:
    return page(
        "1 · Data Ingestion",
        stage_header(1),
        rx.cond(AppState.has_waiting_level2,
                rx.callout(rx.text("Waiting for a community reviewer to confirm: ", AppState.waiting_level2_text),
                           icon="clock", color_scheme="amber", width="100%"),
                rx.fragment()),
        # The facilitator works top to bottom: upload first, the files list after. Everyone else sees files first.
        rx.cond(AppState.role == "facilitator",
                rx.vstack(*intake_tools(), intake_files(), spacing="4", width="100%"),
                rx.vstack(intake_files(), *intake_tools(), spacing="4", width="100%")),
        rx.card(
            rx.heading("Brief", size="3"),
            rx.text(rx.cond(AppState.job_brief != "", AppState.job_brief,
                            "Filled in from the client's spreadsheet when stage 1 runs."),
                    white_space="pre-wrap", size="2"),
            width="100%"),
    )


# ---------------------------------------------------------------- 1 pipeline

def stage_card(s) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.cond(s["done"], rx.icon("circle-check", color="var(--green-9)"), rx.icon("circle", color="gray")),
            rx.vstack(rx.hstack(rx.text(s["n"], " · ", s["name"], weight="bold"),
                                rx.badge(rx.cond(s["done"], "done", "not run yet"), color_scheme="gray"),
                                rx.cond(s["is_waiting"],
                                        rx.badge(rx.icon("user-round-pen", size=12), "waiting: ", s["waiting"],
                                                 color_scheme="amber"),
                                        rx.fragment()),
                                rx.cond(s["has_route"],
                                        rx.link("open", href=s["route"], size="1", color="var(--gray-11)"),
                                        rx.fragment()),
                                spacing="2", align="center", wrap="wrap"),
                      rx.text(rx.text("AI: ", as_="span", weight="medium"), s["ai"], size="1", color="gray"),
                      rx.text(rx.text("Person: ", as_="span", weight="medium"), s["person"], size="1",
                              color="gray"),
                      spacing="1", align="start"),
            rx.spacer(),
            rx.cond(AppState.role == "analyst",
                    rx.button("Run", size="1", variant="outline", on_click=AppState.run_stage(s["n"]),
                              disabled=AppState.running),
                    rx.fragment()),
            align="center", width="100%"),
        width="100%")


def reset_card() -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.text("Reset this job", weight="bold"),
                rx.text("Back to intake: transcripts, artefact readings, themes, sign-off, flags, counts, names and "
                        "reports are removed. The uploaded files, their consent and levels stay.", size="1",
                        color="gray"),
                spacing="1", align="start"),
            rx.spacer(),
            rx.alert_dialog.root(
                rx.alert_dialog.trigger(rx.button("Reset job", color_scheme="red", variant="soft",
                                                  disabled=AppState.running)),
                rx.alert_dialog.content(
                    rx.alert_dialog.title("Reset this job to intake?"),
                    rx.alert_dialog.description(
                        "Everything the stages produced goes, including sign-off decisions and reports. This can't "
                        "be undone. Audio Processing (stage 2) is slow and will have to run again."),
                    rx.hstack(
                        rx.alert_dialog.cancel(rx.button("Cancel", variant="soft")),
                        rx.alert_dialog.action(rx.button("Reset", color_scheme="red", on_click=AppState.reset_job)),
                        spacing="3", justify="end", margin_top="16px"),
                ),
            ),
            align="center", width="100%"),
        width="100%")


def pipeline_page() -> rx.Component:
    return page(
        "Workflow overview",
        rx.text("The stages of PRD §4, in order. Every stage can be re-run. AI stages refuse to run while a "
                "Level 2 file is unconfirmed; stage 4 waits for the name check; stages 7 and 8 wait for "
                "attendance and people counts; stage 8 waits for every identifiability flag.", color="gray"),
        rx.cond(AppState.running,
                rx.callout(rx.text("Stage ", AppState.run_stage_text, " is running — ",
                                    AppState.run_elapsed_text, " elapsed. This page polls every 3 s."),
                           icon="loader", width="100%"),
                rx.fragment()),
        rx.foreach(AppState.stage_names, stage_card),
        rx.card(rx.heading("Job status", size="3"), rx.text(AppState.status_line, size="2"), width="100%"),
        rx.cond(AppState.role == "analyst", reset_card(), rx.fragment()),
        rx.moment(interval=3000, on_change=AppState.poll, display="none"),
    )


# ---------------------------------------------------------------- 2 transcript

def seg_row(s) -> rx.Component:
    return rx.hstack(
        rx.text(s["start_text"], size="1", color="gray", width="52px", min_width="52px"),
        rx.badge(s["speaker_text"], size="1", color_scheme=s["speaker_color"], font_weight="bold"),
        rx.text(s["text"], size="2", color=s["text_color"],
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
        "2 · Audio Processing",
        stage_header(2),
        wordlist_card(),
        rx.hstack(
            rx.text("Recording:"),
            rx.select.root(
                rx.select.trigger(placeholder="Choose a recording", min_width="240px"),
                rx.select.content(rx.foreach(AppState.audio_files,
                                             lambda f: rx.select.item(f["file_id_text"], value=f["id_text"]))),
                value=AppState.selected_file_id.to(str), on_change=AppState.select_file),
            rerun_button(2), align="center"),
        rx.cond(AppState.role == "analyst", rx.card(
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
            rx.cond(AppState.terms_line != "", rx.text(AppState.terms_line, size="2"), rx.fragment()),
            width="100%"), rx.fragment()),
        rx.cond(AppState.speakers_missing,
                rx.callout("Speakers not identified for this recording, so every line shows \"Unknown\" instead of who "
                           "spoke. The analyst can re-run stage 2 to try again.",
                           icon="triangle-alert", color_scheme="amber", width="100%"),
                rx.fragment()),
        rx.hstack(
            rx.card(rx.heading("Polished Transcript (with wordlist)", size="3"),
                    rx.text(AppState.selected_clip, size="1", color="gray"),
                    rx.vstack(rx.foreach(AppState.segments_with, seg_row), spacing="1", max_height="520px",
                              overflow_y="auto"), width="50%"),
            rx.card(rx.heading("Raw Transcript (without wordlist)", size="3"),
                    rx.text(AppState.selected_clip, size="1", color="gray"),
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
        "3 · Image Processing",
        stage_header(3),
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
                  origin_badge(t), rx.badge(t["people_text"], color_scheme="gray"), align="center", wrap="wrap"),
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


def names_file(f) -> rx.Component:
    return rx.card(
        rx.hstack(rx.text(f["filename"], weight="bold", size="2"),
                  rx.cond(f["names_checked"], rx.badge("names checked", color_scheme="green"),
                          rx.button("Names are right", size="1", on_click=AppState.mark_names_checked(f["id"]))),
                  align="center"),
        rx.accordion.root(rx.accordion.item(
            header=rx.text(f["units_header"], size="2"),
            content=rx.vstack(rx.foreach(f["units"].to(list[dict[str, Any]]), lambda u: rx.text(u["line"], size="1")),
                              spacing="1", max_height="260px", overflow_y="auto")),
            collapsible=True, variant="ghost", width="100%"),
        width="100%")


def names_card() -> rx.Component:
    return rx.card(
        rx.heading("Level 2: made-up names", size="3"),
        rx.text("Real names in Level 2 material are swapped for made-up ones before sorting. The list comes from the "
                "word list's @person entries and the local model. Read what sorting will see, add any name that "
                "slipped through, remove anything that isn't a name, then mark each file.", size="1", color="gray"),
        rx.foreach(AppState.names, lambda n: rx.hstack(
            rx.text(n["line"], size="2"),
            rx.button("Remove", size="1", variant="soft", on_click=AppState.remove_name(n["id"])), align="center")),
        rx.hstack(rx.input(value=AppState.new_name, on_change=AppState.set_new_name, placeholder="A name we missed",
                           width="240px"),
                  rx.button("Add name", size="2", on_click=AppState.add_name), align="center"),
        rx.foreach(AppState.name_files, names_file),
        spacing="2", width="100%")


def themes_page() -> rx.Component:
    return page(
        "4 · Draft themes  ·  5 · Evidence check",
        stage_header(4, 5),
        rx.text("Material is sorted into the themes agreed at intake; anything that doesn't fit is grouped into "
                "suggested themes. Quotes come from the sorting, not from the model — it only labels a new group "
                "from its quotes. The evidence check hides any suggested theme whose summary says more than its "
                "quotes do.", color="gray"),
        rx.cond(AppState.has_waiting_names,
                rx.callout(rx.text("Stage 4 won't sort until a person checks the made-up names on: ",
                                   AppState.waiting_names_text),
                           icon="user-check", color_scheme="amber", width="100%"),
                rx.fragment()),
        rx.cond(AppState.has_name_files, names_card(), rx.fragment()),
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
                    rx.text("The community answers these on their own page.", size="1", color="gray"))


def signoff_page() -> rx.Component:
    return page(
        "6 · Community sign-off",
        stage_header(6),
        rx.callout("When the community and the analyst disagree about what material means, the community decides. "
                   "That isn't negotiable.", icon="scale", width="100%"),
        rx.foreach(AppState.themes, lambda t: theme_card(t, actions=True)),
        rx.cond(AppState.role == "community",
                rx.card(rx.heading("Add a theme we missed", size="3"),
                        rx.input(value=AppState.add_label, on_change=AppState.set_add_label, placeholder="Label", width="100%"),
                        rx.text_area(value=AppState.add_summary, on_change=AppState.set_add_summary,
                                     placeholder="What it says", rows="2", width="100%"),
                        rx.hstack(rx.checkbox("Written from Level 3 material (transcribed by hand, no quotes)",
                                              checked=AppState.add_from_level3,
                                              on_change=AppState.set_add_from_level3),
                                  align="center"),
                        rx.cond(AppState.add_from_level3,
                                rx.hstack(rx.text("Level of the wording — it can reach the client, the material never "
                                                  "does", size="1", color="gray"),
                                          rx.select(["1", "2"], value=AppState.add_level,
                                                    on_change=AppState.set_add_level, size="1"),
                                          align="center"),
                                rx.input(value=AppState.add_quote_ids, on_change=AppState.set_add_quote_ids,
                                         placeholder="Quote ids behind it, e.g. 12 15 (from the list below)",
                                         width="100%")),
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


def count_row(t) -> rx.Component:
    return rx.hstack(
        rx.text(t["label"], weight="bold", size="2", min_width="240px"), origin_badge(t),
        rx.text(t["n_people"], " voices heard", size="1", color="gray"),
        rx.cond(AppState.role == "analyst",
                rx.input(default_value=t["count_text"], placeholder="People", width="90px", size="1",
                         on_blur=lambda v: AppState.set_people_count(t["id"], v)),
                rx.text(rx.cond(t["count_text"].to(str) != "", t["count_text"], "not counted"), size="2")),
        align="center", wrap="wrap", width="100%")


def identify_page() -> rx.Component:
    return page(
        "7 · Security Check",
        stage_header(7),
        rx.text("Themes from very few people, and anything that gives someone away. The analyst counts the people "
                "behind each theme by hand — the app can't tell the same person apart across recordings (PRD A6). "
                "Then the flags run. The analyst decides what to cut and writes down why — stage 8 will not run "
                "until every flag has a decision.", color="gray"),
        rx.card(
            rx.heading("People behind each theme", size="3"),
            rx.text("Out of ", AppState.attendance_total_text, " (entered at intake). Type a count and click away "
                    "to save it.", size="1", color="gray"),
            rx.foreach(AppState.signed_off_themes, count_row),
            rx.cond(AppState.has_uncounted,
                    rx.callout(rx.text("Not counted yet: ", AppState.uncounted_text), icon="clock",
                               color_scheme="amber", size="1"),
                    rx.fragment()),
            spacing="2", width="100%"),
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
        "8 · Reporting",
        stage_header(8),
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
        stage_header(9),
        rx.text("A plain-language version for the people who took part. The analyst approves and sends it; "
                "'send' only marks it sent in this prototype. When it goes out, ask participants one yes/no "
                "question: does this match what you said? (PRD §5)", color="gray"),
        rerun_button(9, "Re-draft report-back"),
        rx.cond(AppState.has_reportback,
                rx.vstack(
                    approvals(AppState.reportback),
                    rx.cond(AppState.reportback["sent"], rx.badge("sent", color_scheme="green"),
                            rx.button("Send to participants", on_click=AppState.send_reportback,
                                      disabled=~AppState.can_send | (AppState.role != "analyst"))),
                    rx.card(rx.markdown(AppState.reportback["markdown"].to(str)), width="100%"),
                    width="100%", align="start"),
                rx.text("Not drafted yet.", color="gray")),
    )


# ---------------------------------------------------------------- model settings (analyst)

def model_step_card(st) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(rx.text(st["title"], weight="bold"),
                      rx.cond(st["is_default"], rx.badge("default", color_scheme="gray"), rx.fragment()),
                      rx.cond(st["done"], rx.badge("already run", color_scheme="blue"), rx.fragment()),
                      align="center", spacing="2", wrap="wrap"),
            rx.text(st["does"], size="2", color="gray"),
            rx.cond(
                st["options"].to(list).length() > 0,
                rx.select.root(
                    rx.select.trigger(min_width="320px"),
                    rx.select.content(rx.foreach(st["options"].to(list[dict[str, Any]]),
                                                 lambda o: rx.select.item(o["label"], value=o["name"]))),
                    value=st["chosen"].to(str),
                    on_change=lambda v: AppState.set_model(st["stage"], v)),
                rx.text("No model of this kind on this laptop.", size="2", color="var(--red-11)")),
            rx.cond(st["missing"] & (st["options"].to(list).length() > 0),
                    rx.callout(rx.text(st["chosen_display"], " isn't on this laptop any more. Pick another before this "
                                                     "step runs."), icon="triangle-alert", color_scheme="red",
                               size="1"),
                    rx.fragment()),
            rx.cond(st["heavy"],
                    rx.callout("This model is large for a 16GB laptop. It may run slowly or not load while the "
                               "rest of the app is open.", icon="triangle-alert", color_scheme="amber", size="1"),
                    rx.fragment()),
            rx.cond(st["done"],
                    rx.text("Changing it doesn't touch what this step already made. Re-run it, and the steps "
                            "after it, to use the new model.", size="1", color="gray"),
                    rx.fragment()),
            spacing="2", align="start", width="100%"),
        width="100%")


def model_source_logos() -> rx.Component:
    # Where the local models come from; each logo links to that site in a new tab. Sized to sit inside the heading row.
    return rx.hstack(
        *[rx.link(rx.image(src=f"/{f}", alt=name, height="28px", width="28px", border_radius="6px", object_fit="cover"),
                  href=url, is_external=True, title=name)
          for name, f, url in (("Hugging Face", "logo_huggingface.png", "https://huggingface.co"),
                               ("Ollama", "logo_ollama.jpg", "https://ollama.com"),
                               ("Kaggle", "logo_kaggle.png", "https://www.kaggle.com"))],
        spacing="2", align="center")


def models_page() -> rx.Component:
    return page(
        "Model Configuration",
        rx.text("Which model each step uses for this job. Only models already on this laptop are listed — nothing "
                "is sent outside it. Level 3 material never reaches any model, whatever is picked here. Only you "
                "see this page.", color="gray"),
        rx.cond(AppState.model_error != "",
                rx.callout(AppState.model_error, icon="plug-zap", color_scheme="amber", width="100%"),
                rx.fragment()),
        rx.foreach(AppState.model_steps, model_step_card),
        rx.text("Sign-off (6) has no model: people do it. The chat and the report-back use the default text model.",
                size="1", color="gray"),
        beside_title=model_source_logos(), show_prd_note=False,
    )


# ---------------------------------------------------------------- sign in

def login_page() -> rx.Component:
    # The photo sits on its own layer so only it is blurred; it spills past the edges so the blur has no rim.
    backdrop = rx.box(position="fixed", inset="-12px", z_index="0", background_image="url('/login_page.jpg')",
                      background_size="cover", background_position="center", filter="blur(3px)")
    tint = rx.box(position="fixed", inset="0", z_index="0", background_color="rgba(15, 23, 42, 0.25)")
    return rx.box(backdrop, tint, rx.center(
        rx.vstack(
            rx.hstack(
                rx.center(rx.icon("waypoints", size=20, color="white"), background_color="var(--accent-9)",
                          border_radius="10px", width="40px", height="40px"),
                rx.vstack(rx.heading("VCNITY", size="5", line_height="1"),
                          rx.text("AI-assisted co-design analysis", size="1", color="gray"), spacing="1"),
                align="center", spacing="3"),
            rx.heading("Sign in", size="6", padding_top="8px"),
            rx.form(
                rx.vstack(
                    rx.text("Username", size="2", weight="medium"),
                    rx.input(name="username", placeholder="e.g. sam", size="3", width="100%",
                             auto_focus=True, custom_attrs={"autoComplete": "username"}),
                    rx.text("Password", size="2", weight="medium", padding_top="4px"),
                    rx.input(name="password", type="password", size="3", width="100%",
                             custom_attrs={"autoComplete": "current-password"}),
                    rx.cond(AppState.login_error != "",
                            rx.callout(AppState.login_error, icon="triangle-alert", color_scheme="red", size="1",
                                       width="100%"),
                            rx.fragment()),
                    rx.button("Sign in", type="submit", size="3", width="100%", margin_top="8px"),
                    spacing="2", width="100%"),
                on_submit=AppState.login, width="100%"),
            spacing="3", width="100%", max_width="380px", padding="32px",
            background_color="var(--color-panel-solid)", border_radius="16px",
            box_shadow="0 12px 32px -16px var(--blue-a8)"),
        min_height="100vh", padding="16px", position="relative", z_index="1"),
        min_height="100vh", overflow="hidden", background_color=PAGE_BG)


# ---------------------------------------------------------------- client

def client_page() -> rx.Component:
    """The client researcher: the approved report and nothing else. Never raw data (PRD §3), no quotes (A15)."""
    return rx.box(
        rx.vstack(
            top_bar("Your report", show_jobs=False),  # other jobs are other clients' work
            message_bar(),
            rx.cond(
                AppState.can_export,
                rx.vstack(
                    rx.link(rx.button(rx.icon("download", size=16), "Download .docx"), href=AppState.export_url,
                            is_external=True),
                    rx.card(rx.markdown(AppState.client_report["markdown"].to(str)), width="100%", padding="24px"),
                    width="100%", align="start", spacing="4"),
                rx.callout("Not ready yet. The report shows here once the community and VCNITY have both "
                           "approved it.", icon="clock", width="100%")),
            spacing="4", width="100%", max_width="960px", margin="0 auto", padding="32px 16px"),
        min_height="100vh", background_color=PAGE_BG)


# ---------------------------------------------------------------- app

# Slate greys are blue-tinted, so they sit well on the light blue page; solid panels keep cards white on it.
app = rx.App(theme=rx.theme(accent_color="teal", gray_color="slate", radius="large", panel_background="solid"),
             # the community page's rounded face
             head_components=[rx.el.link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Nunito:"
                                                                "wght@400;500;600;700;800&display=swap")])
for route, component in [("/", intake_page), ("/pipeline", pipeline_page), ("/transcript", transcript_page),
                         ("/artefacts", artefacts_page), ("/themes", themes_page), ("/signoff", signoff_page),
                         ("/identify", identify_page), ("/report", report_page), ("/reportback", reportback_page),
                         ("/community", community_page), ("/client", client_page)]:
    app.add_page(component, route=route, on_load=AppState.load_all, title="VCNITY pipeline")
app.add_page(chat_page, route="/chat", on_load=AppState.load_chat, title="Chat with Data · VCNITY")
app.add_page(login_page, route="/login", on_load=AppState.load_login, title="Sign in · VCNITY")
app.add_page(models_page, route="/models", on_load=[AppState.load_all, AppState.load_models],
             title="Model Configuration · VCNITY")
