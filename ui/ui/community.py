"""The community reviewer's page: one friendly page instead of the stage pages.

Everything a community reviewer does under the PRD, in plain words and nothing else — check the labels
(A9), agree themes and words up front (A17, stage 2), say what made things mean (stage 3), sign off what
we heard (stage 6), and approve the report (stage 8). Its own warm look, on purpose: these are not
technical people and this is not a back office.
"""
from __future__ import annotations

import reflex as rx

from .state import AppState

FONT = "'Nunito', ui-rounded, system-ui, sans-serif"
PAGE_BG = ("radial-gradient(1100px 520px at 0% -10%, var(--orange-3), transparent 60%), "
           "radial-gradient(900px 480px at 100% 0%, var(--grass-3), transparent 55%), var(--sand-2)")
CARD = dict(background_color="var(--color-panel-solid)", border_radius="24px", padding="24px",
            box_shadow="0 1px 2px var(--sand-a4), 0 8px 24px -12px var(--sand-a6)", width="100%")


# ---------------------------------------------------------------- small pieces

def pill(text, colour: str, icon: str | None = None) -> rx.Component:
    return rx.badge(*([rx.icon(icon, size=14)] if icon else []), text, color_scheme=colour, radius="full",
                    size="2", variant="soft", padding="4px 12px")


def needs(count) -> rx.Component:
    return rx.cond(count > 0, pill(rx.text(count, " need", rx.cond(count == 1, "s", ""), " you"), "orange", "hand"),
                   pill("All done", "grass", "check"))


def level_pill(level, name) -> rx.Component:
    return rx.match(level.to(int),
                    (1, pill(name, "grass", "sun")),
                    (2, pill(name, "amber", "heart")),
                    (3, pill(name, "tomato", "lock")),
                    pill(name, "gray"))


def kind_icon(kind, size: int, colour: str) -> rx.Component:
    return rx.match(kind.to(str),
                    ("audio", rx.icon("audio-lines", size=size, color=colour)),
                    ("image", rx.icon("image", size=size, color=colour)),
                    rx.icon("file-text", size=size, color=colour))


def quote_bubble(q) -> rx.Component:
    return rx.box(rx.text("“", q["text"], "”", size="3", line_height="1.55"),
                  background_color="var(--sand-3)", border_radius="18px 18px 18px 4px", padding="12px 16px",
                  width="100%")


def thanks_note(text: str) -> rx.Component:
    return rx.hstack(rx.icon("party-popper", size=22, color="var(--grass-10)"), rx.text(text, size="3"),
                     align="center", spacing="3", padding="16px 20px", border_radius="18px",
                     background_color="var(--grass-3)", width="100%")


def section(anchor: str, n: int, title: str, subtitle: str, status, *children) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.center(str(n), width="40px", height="40px", min_width="40px", border_radius="999px",
                      background_color="var(--orange-9)", color="white", font_weight="800", font_size="18px"),
            rx.vstack(rx.heading(title, size="7", weight="bold"), rx.text(subtitle, size="3", color="gray"),
                      spacing="1", align="start"),
            rx.spacer(),
            status,
            align="center", spacing="4", width="100%", wrap="wrap"),
        *children,
        id=anchor, spacing="4", width="100%", padding_top="24px", scroll_margin_top="16px")


# ---------------------------------------------------------------- top

def top_bar() -> rx.Component:
    return rx.hstack(
        rx.center(rx.icon("heart-handshake", size=20, color="white"), width="40px", height="40px",
                  border_radius="999px", background_color="var(--orange-9)"),
        rx.vstack(rx.text("VCNITY", weight="bold", size="4", line_height="1"),
                  rx.text("Community check", size="2", color="gray", line_height="1"), spacing="1"),
        rx.spacer(),
        rx.cond(AppState.job["name"], pill(AppState.job["name"].to(str), "gray", "folder-heart"), rx.fragment()),
        rx.hstack(rx.icon("circle-user-round", size=18, color="var(--gray-10)"),
                  rx.text(AppState.username, size="2", weight="medium"),
                  rx.button(rx.icon("log-out", size=14), "Sign out", size="2", radius="full", variant="soft",
                            color_scheme="gray", on_click=AppState.logout),
                  align="center", spacing="2"),
        align="center", spacing="3", width="100%", max_width="880px", margin="0 auto", padding="16px",
        wrap="wrap")


def hero() -> rx.Component:
    return rx.vstack(
        rx.heading("Hello, and thank you for helping.", size="8", weight="bold", line_height="1.15"),
        rx.text("People shared their stories, ideas and creations at the sessions, and a computer helped us sort "
                "them. Before anything goes to the client, you check it. When you and VCNITY see something "
                "differently, ", rx.text("you decide what it means.", as_="span", weight="bold"),
                size="4", line_height="1.6"),
        rx.hstack(rx.icon("sparkles", size=18, color="var(--orange-10)"),
                  rx.text(AppState.c_summary, size="3", weight="bold"),
                  align="center", spacing="2", padding="10px 18px", border_radius="999px",
                  background_color="var(--color-panel-solid)", box_shadow="0 1px 2px var(--sand-a4)"),
        spacing="4", align="start", width="100%", padding_y="16px")


def promise() -> rx.Component:
    return rx.hstack(
        rx.center(rx.cond(AppState.audit_ok, rx.icon("shield-check", size=24, color="var(--grass-11)"),
                          rx.icon("shield-alert", size=24, color="var(--tomato-11)")),
                  width="48px", height="48px", min_width="48px", border_radius="999px",
                  background_color=rx.cond(AppState.audit_ok, "var(--grass-4)", "var(--tomato-4)")),
        rx.vstack(
            rx.text("Our promise to you", weight="bold", size="3"),
            rx.cond(AppState.audit_ok,
                    rx.text("Nothing marked Restricted has been near the computer's AI. We check this every time.",
                            size="2", color="gray"),
                    rx.text("Something marked Restricted reached the computer's AI. Please tell VCNITY "
                            "straight away.", size="2", color="var(--tomato-11)", weight="bold")),
            spacing="1", align="start"),
        align="center", spacing="4", **CARD)


def step_nav() -> rx.Component:
    def step(n: int, label: str, anchor: str, done) -> rx.Component:
        return rx.link(
            rx.hstack(rx.cond(done, rx.icon("circle-check", size=16, color="var(--grass-10)"),
                              rx.text(str(n), weight="bold", color="var(--orange-11)")),
                      rx.text(label, size="2", weight="medium"), align="center", spacing="2"),
            href=f"#{anchor}", underline="none", color="inherit", padding="8px 14px", border_radius="999px",
            background_color="var(--color-panel-solid)", box_shadow="0 1px 2px var(--sand-a4)",
            _hover={"background_color": "var(--orange-3)"})

    return rx.hstack(
        step(1, "Check the labels", "labels", AppState.c_waiting_count == 0),
        step(2, "Our words", "words", AppState.agreed_themes.length() > 0),
        step(3, "Things people made", "made", AppState.c_artefacts_left == 0),
        step(4, "What we heard", "heard", (AppState.c_theme_total > 0) & (AppState.c_open_count == 0)),
        step(5, "The report", "report", AppState.has_client_report & ~AppState.c_report_waiting),
        spacing="2", wrap="wrap", width="100%")


def message() -> rx.Component:
    return rx.cond(
        AppState.message != "",
        rx.hstack(
            rx.cond(AppState.message_kind == "error", rx.icon("circle-alert", size=20, color="var(--tomato-11)"),
                    rx.icon("heart", size=20, color="var(--grass-11)")),
            rx.text(AppState.message, size="3"),
            align="center", spacing="3", padding="14px 20px", border_radius="18px", width="100%",
            position="sticky", top="12px", z_index="10", box_shadow="0 8px 24px -12px var(--sand-a8)",
            background_color=rx.cond(AppState.message_kind == "error", "var(--tomato-3)", "var(--grass-3)")),
        rx.fragment())


# ---------------------------------------------------------------- 1 labels

def preview(f) -> rx.Component:
    return rx.match(
        f["kind"].to(str),
        ("audio", rx.el.audio(src=f["media_url"], controls=True, preload="none", style={"width": "100%"})),
        ("image", rx.image(src=f["media_url"], max_height="260px", max_width="100%", border_radius="16px",
                           object_fit="cover")),
        ("text", rx.cond(f["has_preview"],
                         rx.box(rx.text(f["preview"], "…", size="2", white_space="pre-wrap", line_height="1.6"),
                                max_height="160px", overflow_y="auto", padding="12px 16px", border_radius="16px",
                                background_color="var(--sand-3)", width="100%"),
                         rx.link("Open the file to read it", href=f["media_url"], is_external=True, size="2"))),
        rx.fragment())


def label_card(f) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.center(kind_icon(f["kind"], 22, "var(--orange-11)"), width="44px", height="44px",
                      min_width="44px", border_radius="14px", background_color="var(--orange-3)"),
            rx.text(f["name"], weight="bold", size="4", word_break="break-word"),
            rx.spacer(),
            level_pill(f["level"], f["level_name"]),
            align="center", spacing="3", width="100%", wrap="wrap"),
        rx.text(f["level_meaning"], size="3", color="gray"),
        preview(f),
        rx.text("Is this the right label?", weight="bold", size="3", padding_top="4px"),
        rx.hstack(
            rx.button(rx.icon("check", size=18), "Yes, that's right", size="3", radius="full", color_scheme="grass",
                      on_click=AppState.confirm_file(f["id"])),
            spacing="3", wrap="wrap"),
        rx.text("Not right? Ask the facilitator or the analyst to change the label, then check it again here.",
                size="2", color="gray"),
        spacing="3", align="start", **CARD)


def file_line(f) -> rx.Component:
    return rx.hstack(
        kind_icon(f["kind"], 18, "var(--gray-10)"),
        rx.text(f["name"], size="3", word_break="break-word"),
        rx.spacer(),
        level_pill(f["level"], f["level_name"]),
        align="center", spacing="3", width="100%", wrap="wrap", padding_y="8px",
        border_bottom="1px solid var(--sand-4)")


def labels_section() -> rx.Component:
    return section(
        "labels", 1, "Check the labels",
        "Every file has a label that decides what the computer may do with it. Nothing labelled Sensitive is "
        "touched until you say the label is right.",
        needs(AppState.c_waiting_count),
        rx.cond(AppState.c_waiting_count == 0,
                thanks_note("Every label is checked. Thank you!"),
                rx.foreach(AppState.c_files_waiting, label_card)),
        rx.box(rx.accordion.root(rx.accordion.item(
            header=rx.text("See every file and its label", size="3", weight="medium"),
            content=rx.vstack(
                rx.text("Only the facilitator or the analyst can change a label. If one looks wrong, tell them.",
                        size="2", color="gray"),
                rx.foreach(AppState.c_files, file_line), spacing="1", width="100%")),
            collapsible=True, variant="ghost", width="100%"), **CARD),
    )


# ---------------------------------------------------------------- 2 our words

def agreed_chip(t) -> rx.Component:
    return rx.tooltip(pill(t["label"], "orange", "tag"), content=t["summary"].to(str))


def word_chip(w) -> rx.Component:
    return rx.hstack(
        rx.text(w["term"], size="2", weight="medium"),
        rx.cond(w["is_name"], rx.text("name", size="1", color="var(--orange-11)"), rx.fragment()),
        rx.icon("x", size=14, cursor="pointer", color="var(--gray-10)", on_click=AppState.remove_word(w["i"])),
        align="center", spacing="2", padding="6px 8px 6px 14px", border_radius="999px",
        background_color="var(--sand-3)")


def words_section() -> rx.Component:
    themes_card = rx.vstack(
        rx.heading("Themes to sort into", size="5"),
        rx.text("Agree these before anything is sorted. Everything people said goes under one of them, and the "
                "computer suggests new ones only where something doesn't fit.", size="2", color="gray"),
        rx.cond(AppState.agreed_themes.length() > 0,
                rx.hstack(rx.foreach(AppState.agreed_themes, agreed_chip), wrap="wrap", spacing="2"),
                rx.text("No themes yet.", size="2", color="gray", font_style="italic")),
        rx.input(value=AppState.agreed_label, on_change=AppState.set_agreed_label, placeholder="Theme name",
                 size="3", radius="full", width="100%"),
        rx.text_area(value=AppState.agreed_summary, on_change=AppState.set_agreed_summary,
                     placeholder="What it covers, in your own words", rows="2", size="3", width="100%"),
        rx.hstack(rx.switch(checked=AppState.agreed_level == "2", on_change=AppState.set_agreed_identifying,
                            color_scheme="orange"),
                  rx.text("Could this wording identify someone?", size="2"), align="center", spacing="2"),
        rx.button(rx.icon("plus", size=16), "Add theme", size="3", radius="full",
                  on_click=AppState.add_agreed_theme),
        rx.cond(AppState.job_brief != "",
                rx.accordion.root(rx.accordion.item(
                    header=rx.text("What the client asked us", size="2", weight="medium"),
                    content=rx.text(AppState.job_brief, size="2", white_space="pre-wrap", color="gray")),
                    collapsible=True, variant="ghost", width="100%"),
                rx.fragment()),
        spacing="3", align="start", **CARD)

    words_card = rx.vstack(
        rx.heading("Words we should know", size="5"),
        rx.text("Names, slang and local place words. They help the computer hear them right in the recordings.",
                size="2", color="gray"),
        rx.cond(AppState.wordlist_items.length() > 0,
                rx.hstack(rx.foreach(AppState.wordlist_items, word_chip), wrap="wrap", spacing="2"),
                rx.text("No words yet.", size="2", color="gray", font_style="italic")),
        rx.hstack(rx.input(value=AppState.new_word, on_change=AppState.set_new_word, placeholder="A word or name",
                           size="3", radius="full", flex="1", min_width="160px"),
                  rx.button(rx.icon("plus", size=16), "Add", size="3", radius="full", on_click=AppState.add_word),
                  width="100%", spacing="2"),
        rx.hstack(rx.checkbox(checked=AppState.new_word_is_name, on_change=AppState.set_new_word_is_name,
                              color_scheme="orange"),
                  rx.text("This is someone's name — swap it for a made-up one in Sensitive material", size="2"),
                  align="center", spacing="2"),
        spacing="3", align="start", **CARD)

    return section("words", 2, "Our words", "The themes and words that matter to your community.",
                   pill(rx.text(AppState.agreed_themes.length(), " themes agreed"), "gray", "tag"),
                   rx.grid(themes_card, words_card, columns=rx.breakpoints(initial="1", md="2"), spacing="4",
                           width="100%", align_items="start"))


# ---------------------------------------------------------------- 3 things people made

def made_card(a) -> rx.Component:
    return rx.flex(
        rx.image(src=a["image_url"], width=rx.breakpoints(initial="100%", sm="220px"), height="auto",
                 border_radius="18px", object_fit="cover", flex_shrink="0"),
        rx.vstack(
            rx.text(a["name"], weight="bold", size="4", word_break="break-word"),
            rx.text("What did the maker say it means?", size="3", weight="medium"),
            rx.cond(AppState.maker_edit_id == a["id"].to(int),
                    rx.vstack(rx.text_area(value=AppState.maker_edit_text, on_change=AppState.set_maker_edit_text,
                                           placeholder="In the maker's own words", rows="4", size="3",
                                           width="100%"),
                              rx.button(rx.icon("check", size=16), "Save", size="3", radius="full",
                                        on_click=AppState.save_maker),
                              width="100%", align="start"),
                    rx.cond(a["has_statement"],
                            rx.vstack(quote_bubble({"text": a["maker_statement"]}),
                                      rx.button("Change", size="2", radius="full", variant="soft",
                                                on_click=AppState.start_maker_edit(a["id"], a["maker_statement"])),
                                      width="100%", align="start"),
                            rx.button(rx.icon("pencil", size=16), "Tell us what it means", size="3", radius="full",
                                      on_click=AppState.start_maker_edit(a["id"], a["maker_statement"])))),
            rx.accordion.root(rx.accordion.item(
                header=rx.text("What the computer saw (it never guesses meaning)", size="2", color="gray"),
                content=rx.vstack(rx.text(a["verbatim_text"], size="2", white_space="pre-wrap"),
                                  rx.text(a["description"], size="2", color="gray"), spacing="2")),
                collapsible=True, variant="ghost", width="100%"),
            spacing="3", align="start", width="100%"),
        direction=rx.breakpoints(initial="column", sm="row"), spacing="5", **CARD)


def made_section() -> rx.Component:
    return section(
        "made", 3, "Things people made",
        "Only the maker knows what their work means. The computer just describes what's in the photo.",
        needs(AppState.c_artefacts_left),
        rx.cond(AppState.artefacts.length() > 0,
                rx.foreach(AppState.c_artefacts, made_card),
                rx.text("No photos in this job yet.", size="3", color="gray")))


# ---------------------------------------------------------------- 4 what we heard

def status_pill(t) -> rx.Component:
    return rx.match(t["status"].to(str),
                    ("draft", pill(t["status_words"], "orange", "hand")),
                    ("rejected", pill(t["status_words"], "tomato", "x")),
                    ("cut", pill(t["status_words"], "gray", "eye-off")),
                    pill(t["status_words"], "grass", "check"))


def answer_buttons(t) -> rx.Component:
    def three(size: str):
        return rx.hstack(
            rx.button(rx.icon("thumbs-up", size=16), "That's right", size=size, radius="full", color_scheme="grass",
                      on_click=AppState.review(t["id"], "confirm")),
            rx.button(rx.icon("pencil", size=16), "Fix the wording", size=size, radius="full", color_scheme="amber",
                      variant="soft", on_click=AppState.start_fix(t["id"], t["label"], t["summary"])),
            rx.button(rx.icon("thumbs-down", size=16), "That's not right", size=size, radius="full",
                      color_scheme="tomato", variant="soft", on_click=AppState.review(t["id"], "reject")),
            spacing="2", wrap="wrap")

    fix_form = rx.vstack(
        rx.input(value=AppState.fix_label, on_change=AppState.set_fix_label, placeholder="Theme name", size="3",
                 radius="full", width="100%"),
        rx.text_area(value=AppState.fix_summary, on_change=AppState.set_fix_summary,
                     placeholder="What it says, in your words", rows="3", size="3", width="100%"),
        rx.input(value=AppState.fix_note, on_change=AppState.set_fix_note, placeholder="Why? (you don't have to say)",
                 size="3", radius="full", width="100%"),
        rx.hstack(rx.button("Save my wording", size="3", radius="full", on_click=AppState.review(t["id"], "fix")),
                  rx.button("Cancel", size="3", radius="full", variant="soft", color_scheme="gray",
                            on_click=AppState.cancel_fix), spacing="2"),
        width="100%", spacing="2", padding="16px", border_radius="18px", background_color="var(--amber-2)")

    return rx.cond(
        AppState.fix_id == t["id"].to(int), fix_form,
        rx.cond(t["status"].to(str) == "cut", rx.fragment(),
                rx.cond(t["is_open"], three("3"),
                        rx.vstack(rx.text("Changed your mind?", size="2", color="gray"), three("1"),
                                  spacing="1", align="start"))))


def heard_card(t) -> rx.Component:
    return rx.vstack(
        rx.hstack(status_pill(t), pill(t["people"], "gray", "users"), spacing="2", wrap="wrap"),
        rx.heading(t["label"], size="6", weight="bold"),
        rx.text(t["summary"], size="3", line_height="1.6"),
        rx.hstack(rx.icon("info", size=14, color="var(--gray-10)"), rx.text(t["origin"], size="2", color="gray"),
                  align="center", spacing="2"),
        rx.cond(t["has_quotes"],
                rx.vstack(rx.text("What people said", size="2", weight="bold", color="gray"),
                          rx.foreach(t["quotes_top"].to(list[dict]), quote_bubble),
                          rx.cond(t["has_rest"],
                                  rx.accordion.root(rx.accordion.item(
                                      header=rx.text(t["rest_header"], size="2"),
                                      content=rx.vstack(rx.foreach(t["quotes_rest"].to(list[dict]), quote_bubble),
                                                        spacing="2", width="100%")),
                                      collapsible=True, variant="ghost", width="100%"),
                                  rx.fragment()),
                          spacing="2", width="100%"),
                rx.fragment()),
        answer_buttons(t),
        spacing="3", align="start", **CARD,
        border_left=rx.cond(t["is_open"], "6px solid var(--orange-9)", "6px solid transparent"))


def unit_row(u) -> rx.Component:
    return rx.hstack(
        rx.cond(u["picked"], rx.icon("square-check", size=20, color="var(--orange-10)", flex_shrink="0"),
                rx.icon("square", size=20, color="var(--gray-8)", flex_shrink="0")),
        rx.text(u["text"], size="2"),
        align="start", spacing="3", width="100%", padding="8px 10px", border_radius="12px", cursor="pointer",
        background_color=rx.cond(u["picked"], "var(--orange-3)", "transparent"),
        _hover={"background_color": "var(--sand-3)"}, on_click=AppState.toggle_pick(u["id"]))


def missed_card() -> rx.Component:
    return rx.vstack(
        rx.hstack(rx.icon("lightbulb", size=22, color="var(--orange-10)"),
                  rx.heading("Did we miss something?", size="5"), align="center", spacing="2"),
        rx.text("Add anything the computer missed. It goes in the report like any other theme.", size="2",
                color="gray"),
        rx.input(value=AppState.add_label, on_change=AppState.set_add_label, placeholder="Theme name", size="3",
                 radius="full", width="100%"),
        rx.text_area(value=AppState.add_summary, on_change=AppState.set_add_summary,
                     placeholder="What people were saying, in your words", rows="3", size="3", width="100%"),
        rx.hstack(rx.switch(checked=AppState.add_from_level3, on_change=AppState.set_add_from_level3,
                            color_scheme="orange"),
                  rx.text("This comes from Restricted material (it goes without quotes)", size="2"),
                  align="center", spacing="2"),
        rx.hstack(rx.switch(checked=AppState.add_level == "2", on_change=AppState.set_add_identifying,
                            color_scheme="orange"),
                  rx.text("Could this wording identify someone?", size="2"), align="center", spacing="2"),
        rx.cond(~AppState.add_from_level3,
                rx.vstack(
                    rx.text("Pick what people said that backs it up", size="3", weight="medium"),
                    rx.input(rx.input.slot(rx.icon("search", size=16)), value=AppState.unit_search,
                             on_change=AppState.set_unit_search, placeholder="Search what people said, e.g. bus",
                             size="3", radius="full", width="100%"),
                    rx.text(AppState.c_pick_text, size="2", color="gray"),
                    rx.cond(AppState.unit_search != "",
                            rx.vstack(rx.foreach(AppState.c_units, unit_row), spacing="1", width="100%",
                                      max_height="300px", overflow_y="auto"),
                            rx.fragment()),
                    spacing="2", width="100%"),
                rx.fragment()),
        rx.button(rx.icon("plus", size=16), "Add this theme", size="3", radius="full", on_click=AppState.add_theme),
        spacing="3", align="start", **CARD, border="2px dashed var(--orange-6)")


def heard_section() -> rx.Component:
    return section(
        "heard", 4, "What we heard",
        "The computer grouped what people said into themes. Is each one right? Your answer is final.",
        needs(AppState.c_open_count),
        rx.cond(AppState.c_theme_total > 0,
                rx.vstack(
                    rx.hstack(rx.progress(value=AppState.c_progress, color_scheme="grass", size="3", flex="1"),
                              rx.text(AppState.c_progress_text, size="2", weight="bold", white_space="nowrap"),
                              align="center", spacing="3", width="100%"),
                    rx.foreach(AppState.c_themes, heard_card),
                    spacing="4", width="100%"),
                rx.text("Nothing to look at yet. Themes show up here once the material has been sorted.", size="3",
                        color="gray")),
        missed_card())


# ---------------------------------------------------------------- 5 the report

def report_section() -> rx.Component:
    r = AppState.client_report
    approve = rx.alert_dialog.root(
        rx.alert_dialog.trigger(rx.button(rx.icon("stamp", size=18), "I approve this report", size="4",
                                          radius="full", color_scheme="grass")),
        rx.alert_dialog.content(
            rx.alert_dialog.title("Approve the report?"),
            rx.alert_dialog.description("You're approving it for the community. It goes to the client once VCNITY "
                                        "approves it too."),
            rx.hstack(rx.alert_dialog.cancel(rx.button("Not yet", variant="soft", color_scheme="gray",
                                                       radius="full")),
                      rx.alert_dialog.action(rx.button("Approve", color_scheme="grass", radius="full",
                                                       on_click=AppState.approve(r["id"]))),
                      spacing="3", justify="end", margin_top="16px")))
    return section(
        "report", 5, "The report",
        "This is what the client gets. No names and no quotes, only the themes you signed off.",
        rx.cond(AppState.c_report_waiting, pill("Needs you", "orange", "hand"),
                rx.cond(AppState.has_client_report, pill("Approved", "grass", "check"), rx.fragment())),
        rx.cond(
            AppState.has_client_report,
            rx.vstack(
                rx.box(rx.markdown(r["markdown"].to(str)), **{**CARD, "padding": "32px"}),
                rx.cond(r["approved_community"],
                        thanks_note("You approved this report for the community."),
                        approve),
                rx.hstack(rx.cond(r["approved_analyst"], rx.icon("circle-check", size=16, color="var(--grass-10)"),
                                  rx.icon("clock", size=16, color="var(--gray-10)")),
                          rx.text(rx.cond(r["approved_analyst"], "VCNITY has approved it too.",
                                          "VCNITY hasn't approved it yet."), size="2", color="gray"),
                          align="center", spacing="2"),
                spacing="4", width="100%", align="start"),
            rx.text("The report comes here once the themes are signed off and VCNITY has written it up.", size="3",
                    color="gray")))


# ---------------------------------------------------------------- page

def community_page() -> rx.Component:
    return rx.theme(
        rx.box(
            top_bar(),
            rx.vstack(
                hero(), message(), promise(), step_nav(),
                labels_section(), words_section(), made_section(), heard_section(), report_section(),
                rx.center(rx.text("VCNITY · your material, your say", size="2", color="gray"), width="100%",
                          padding_y="32px"),
                spacing="4", width="100%", max_width="880px", margin="0 auto", padding="0 16px 32px"),
            min_height="100vh", background=PAGE_BG, font_family=FONT,
            style={"--default-font-family": FONT, "--heading-font-family": FONT}),
        accent_color="orange", gray_color="sand", radius="full", has_background=False)
