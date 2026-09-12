# VCNITY 2026 AI Project — PRD Workspace + Prototype

This repo is two things for an IFN735 industry/capstone project: a **Product Requirements Document (PRD)** for VCNITY's 2026 AI project, and a **working prototype** of the pipeline it describes — an AI-assisted analysis pipeline that turns messy Creative Co-Design material (multi-speaker audio, code-switched languages, local slang, photos of handmade artefacts) into policy-ready themes, without letting AI override community authority over meaning.

This README orients you to both — the PRD conventions below, and a look at what the prototype does before you follow the link to actually run it.

## Prototype app — quickstart

The app lives in `app/` and runs the PRD's full ten-stage pipeline (§4) end to end: intake → transcription → theme drafting → community sign-off → a council-style report, with two hard rules enforced in code, not just on paper — Level 3 material never reaches any AI model, and an analyst can never override a community decision.

![The prototype's Intake page — every file gets a consent record and a sensitivity level before anything runs on it](Image/index_page.jpg)

**Install steps, prerequisites, the demo script, and what each stage proves live in one place — [`app/README.md`](app/README.md).** (Kept out of this file so there's a single source of truth instead of two copies to keep in sync.)

## Getting the files

This folder is synced via Google Drive, and also tracked in git so changes can be reviewed as diffs. To get a working copy:

```
git clone <repo-url>
```

Most of the working content (`PRD/`, `Document/`, `Docs/`, `Data/`, `Assessment1/`) is currently **untracked** in git — it lives on disk/Drive but hasn't been committed yet. If you're joining via git alone, ask a teammate to share the Drive folder directly, or check `git status` after cloning to see what's missing locally.

## What's where

- **`PRD/VCNITY_PRD_v0.3.md`** — the live PRD, the working source of truth. `v0.2` sits alongside it as the immediately-prior draft, kept for reference — don't edit it.
- **`app/`** — the prototype app (see the quickstart above and `app/README.md`).
- **`PRD/VCNITY-PRD-Clarification-Questions.md`** — numbered open questions for the product owner, grouped by topic.
- **`Document/VCNITY 2026 AI project.pdf`** — the client's pitch deck. Every requirement in the PRD should trace back to a slide in here.
- **`Document/VCNITY_Technical_Workflow_Proposal_Shafwon.pdf`** — the team's own wider-platform sketch. Not submitted, not committed to — don't treat it as scope.
- **`Document/`** — client correspondence and unit IP terms.
- **`Assessment1/`** — the assessment 1 pitch/proposal deliverables (proposal draft, technical solution sections, pitch deck).
- **`Data/Raw/`** — raw source material for analysis.
- **`Docs/superpowers/`** — implementation-plan records for document revisions (e.g. deck-to-PRD alignment history). Worth reading before a large PRD revision.
- **`CLAUDE.md`** — the authoritative guide to how this repo is organised and how the PRD must be written (voice, scope boundaries, assumption-marker rules). Read this before editing the PRD.

## How to review/verify a change

There's no test command. "Verification" here means:

1. **Re-read the PRD** after any edit — check it against the deck (`Document/VCNITY 2026 AI project.pdf`) so every requirement still traces to a slide.
2. **Check the assumption markers.** Every `` `[A1]` ``…`` `[An]` `` inline marker in the PRD must have a matching row in the §9 assumption table, and vice versa. After adding/removing one, renumber and check both directions — `grep -n '\[A[0-9]' PRD/VCNITY_PRD_v0.3.md` is a quick way to list them all.
3. **Check scope stayed pipeline-only.** Community hub, ideas board, public pages, job matching, billing, SROI numbers, engagement analytics, moderation, retention after a job, and AI distress detection are explicitly out of scope — flag anything that creeps toward these.
4. **Preserve the two non-negotiable rules:** when community and analyst disagree about what material *means*, the community decides; and Level 3 sensitivity material reaching an outside AI service is zero, no exceptions. Confirm both survived your edit.
5. **Don't reword/reorder/delete existing sentences as a side effect** of an unrelated change — diff your edit (`git diff`) and make sure unrelated lines didn't move.

## Git conventions

- Current branch: `master`. `main` is the PR base.
- Commits use conventional style scoped to the document, e.g. `docs(prd): trim to the deliverable core`, with a body explaining what was cut/added and why, plus a line-count delta.
- `git log` on the PRD's pre-move history needs the old filename (`VCNITY-2026-AI-PRD-DRAFT.md`) — see `CLAUDE.md` for the full story on the file move.

## Don't touch

- `Archive/` — excluded on purpose (`.claudeignore` / `.gitignore`). Leave it alone unless someone points at a specific file inside it.
- `LEC*/`, `TUT*/` — unit teaching material, not project material.
- `~WRL*.tmp` — Word autosave leftovers, safe to ignore.
