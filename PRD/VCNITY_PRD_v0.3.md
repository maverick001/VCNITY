# VCNITY v0.3

## Product Requirements Document

## 1. The Problem Statement

Creative Co-Design involves a lot of aspects — people talking over each other, switching languages, local slang, things they've made by hand. Going through it by hand is too slow. Letting AI do it alone is worse because AI may not be albe to always get local culture right, and if it interprets community knowledge unwatched, the trust of our client will collapse. 



## 2. What we're building

We want to build an application that utilizes AI for the heavy lifting, lets people make the real decisions, and enables the community keep authority over what their own material means. The app needs to balance those three aspects.

Main features of the application:

1. **Transcription that copes with how people actually talk** — multiple speakers, switched languages, local slang — improved by a word list the community gives us. This is the part we're testing and the main research result.
2. **Draft themes, every one traceable to a real quote.** Claims that don't trace get thrown out before a person ever sees them.
3. **Community sign-off.** The community confirms, fixes, rejects, or adds what we missed, before anything reaches the client.
4. **Sensitivity levels that decide what AI may touch**. This should be set at intake and enforced the whole way through.
5. **A reporting function.** Slide 11 calls this "THE MUST!". We can build the mechanism.

Text also comes in — slides, Word files, plain text — and goes through the same pipeline as audio and photos. See §7.

**What we're handing over** `[A1]` — a proof of concept, not a live system holding real community data. 

**Out** — the community hub, ideas board, public pages, job matching, billing, SROI numbers, engagement analytics ("who is not connecting"), moderation, keeping insights after a job ends, and AI spotting distress `[A2]`. 



## 3. Who uses the App

| User Groups             | What they need                                                                                        |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| **Facilitator**         | Upload fast, mark how sensitive it is without legal training, do no analyst work                      |
| **Community reviewers** | See what the AI said about them in plain words, fix it, and have the fix stick                        |
| **VCNITY analyst**      | Only see what needs a person, settle disagreements between reviewers, approve what goes out           |
| **Client researcher**   | Themes they can put in a policy paper, tied to their brief, with quotes they can cite. Never raw data |
| **Participant**         | Not misquoted, not recognisable, and told plainly what came of it                                     |

## 

## 4. The Data Pipeline

| #   | Stage                           | AI functions                                                                                           | Human in the loop                                                                                                       |
| --- | ------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| 0   | **Intake**                      | —                                                                                                      | Ties every file to a consent record and a sensitivity level. Nothing gets in without both                               |
| 1   | **Ingest**                      | Converts formats, records where it came from                                                           | —                                                                                                                       |
| 2   | **Transcription**               | Speech to text, works out who's speaking, copes with people switching languages, scores how sure it is | Community gives us a **word list** — names, slang, local place words. Anything the AI isn't sure about goes to a person |
| 3   | **Things people made**          | Describes what's in the photo, nothing more                                                            | Meaning comes from what the maker said about their own work. AI never guesses what art means                            |
| 4   | **Draft themes**                | Groups related bits into *draft* themes, each linked to its quotes                                     | —                                                                                                                       |
| 5   | **Evidence check**              | Checks every claim traces to a real quote, throws out the ones that don't                              | —                                                                                                                       |
| 6   | **Community sign-off**          | —                                                                                                      | Community confirms, fixes, rejects, or adds what we missed. **What they say goes**                                      |
| 7   | **Could anyone be identified?** | Flags themes that come from very few people, and anything that gives someone away                      | Analyst decides what to cut, and writes down why                                                                        |
| 8   | **Report**                      | Drafts recommendations against the brief                                                               | Analyst edits. Community and analyst both approve before it leaves                                                      |
| 9   | **Report back**                 | Drafts a plain-language version for participants                                                       | Approves and sends it                                                                                                   |

Note: when the community and the analyst disagree about what material *means*, the community decides — that isn't negotiable. 

Text files skip stages 2 and 3. Stage 1 pulls the words out and they go straight to stage 4. Pictures inside a slide deck go through stage 3 like any photo.

**The sensitivity levels, as we've built them** `[A3]`:

| Level            | What's in it                                                                            | What's allowed                                                               |
| ---------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **1 Open**       | General comments about places, services, surroundings                                   | AI can analyse it                                                            |
| **2 Sensitive**  | Personal experience, health and wellbeing, anything tied to a known group               | Only after names and details are stripped out, and a person must check it    |
| **3 Restricted** | First Nations cultural knowledge, disclosures of harm, anything the community restricts | **No AI at all.** People only, community decides. May never reach the client |

The facilitator sets it on upload. The community can raise it any time. Nothing lowers it automatically. If the facilitator isn't sure, it goes up a level. And nothing above Level 1 goes near AI until someone from the community has confirmed the level `[A4]` — we don't know who that person is on a real job. Level 3 is hand work, and that's what a job costs `[A5]` — we don't know what share of a typical job is Level 3.

"Very few people" in stage 7 means fewer than 3 `[A6]`. The number is a placeholder.

## 5. Benchmark App perforamce

| Measure                                                                                          | Target                                                                 |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| Transcription mistakes on local and multilingual speech, with the community word list vs without | A clear improvement — *this is the main research result*               |
| Draft themes the community accepts, or accepts after fixing                                      | 70% or better                                                          |
| Claims with nothing behind them that still reach a reviewer                                      | Under 5%                                                               |
| Level 3 material reaching an outside AI service                                                  | **Zero. No exceptions**                                                |
| Participants who say the report matches what they said                                           | Checked each pilot                                                     |
| Themes the community added that the AI missed entirely                                           | Tracked every job — a rising number means the model is playing it safe |

The first measure needs a transcript a person has corrected by hand, for at least one recording per pilot. Without it we can show what the word list changed, not whether it was right.

## 

## 6. Safety and the law

We assumed the Privacy Act and the CARE principles apply, the data can't leave Australia, and Level 3 is blocked from anything outside `[A7]`. Everything in the prototype runs on one laptop and no material leaves it. That makes the zero in §5 a fact we can show, not a promise.

## 7. Text and other material

You've told us to expect slides, Word files and plain text alongside the recordings and photos. Pulling the words out of those needs no AI. What we don't know is whose words they are `[A8]` — a facilitator's notes, something a participant wrote, or your brief to us are three different things. We've treated them all like any other file: they need a consent record and a level at intake, and the brief sits at Level 1.

**What the sample material taught us.** The three photos we were given are 480 by 360 pixels — copies that went through a messaging app. The big marker words are readable. The small handwriting isn't, and no model can recover what the picture doesn't hold. The recordings are from the back of a room, quiet and noisy. So two capture rules for the pilot: photos come as the original file, not through Messages or WhatsApp; and one phone sits near whoever is speaking. Both are cheaper than anything we can do afterwards.

## 8. The reporting function

You sent us four Ipswich City Council engagement projects as reporting examples. Their reports follow one shape: why we engaged, how we engaged, what the community told us, findings. Open answers come out as a table — theme, then "4 of 10 respondents (40%)", then a line of summary — using one set of themes across the whole job. No one is quoted. No one is named.

That tells us four things we'd guessed differently, and we'd rather you settled them than we did.

**Which "reporting function" you meant** `[A9]` — slide 11 could mean the report that goes to the client, or a way for someone to raise a concern. Your examples are the first. The prototype has both: the report, and a "raise a concern" button on every screen. Tell us which one is THE MUST.

**Quotes** `[A10]` — your examples carry none. Our whole method rests on them: every theme traces to a real quote, and the client researcher in §3 wants "quotes they can cite". We've assumed quotes go to the client. If they don't, they still do their job inside the pipeline as evidence, and the client gets the table.

**One person behind a theme** `[A11]` — your examples report "1 of 8 respondents". Our rule in stage 7 drops anything under 3 people. Ours is more careful than your habit. We kept ours.

**One set of themes for the job** `[A12]` — the council reuses the same themes across every question and every suburb. The AI finds whatever groups the material falls into. We've assumed the community approves one set of themes for a job, and everything gets sorted into those. That's more work at sign-off and a cleaner report.

**Who gets a concern, and how fast** `[A13]` — the older draft guessed: harm goes to a named person at VCNITY the same business day, everything else to the analyst within five business days. Those are placeholders and they're a promise you make to a community. One ask regardless: a named person who owns harm reports, in post before the first pilot session. Not a role, not a shared inbox.

## 9. Questions

| ID  | What we assumed                                                        | Importance                                              | Comment                                                                                        |
| --- | ---------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| A1  | Proof of concept, not live with real community data                    | **Severe** — sets the security bar                      |                                                                                                |
| A2  | We're only building the four things in §2                              | **Severe** — different project                          |                                                                                                |
| A3  | The three sensitivity levels as written                                | Moderate                                                | Level 3 as written means no AI at all, including our own local model. The prototype enforces that |
| A4  | Who confirms a level before AI runs                                    | Moderate — it's what makes the §5 zero real             | Prototype: a community reviewer ticks it on the intake screen                                  |
| A5  | What share of a typical job is Level 3                                 | **Severe** — decides whether the price works            |                                                                                                |
| A6  | Drop themes with fewer than 3 people behind them                       | Moderate                                                | See A11 — your examples do the opposite                                                        |
| A7  | Privacy Act and CARE apply                                             | **Severe** — compliance                                 |                                                                                                |
| A8  | Text files are treated like any other file, brief is Level 1           | Moderate                                                | Whose words are they decides consent                                                           |
| A9  | "Reporting function" means the client report, and we built a concern button too | **Severe** — it's THE MUST and we're not sure what it is |                                                                               |
| A10 | Quotes go to the client                                                | Moderate — the table works either way                   | Your examples have none                                                                        |
| A11 | We drop one-person themes even though your examples report them        | Moderate                                                | Same rule as A6, seen from your side                                                           |
| A12 | One community-approved set of themes per job                           | Moderate — more sign-off work, cleaner report           |                                                                                                |
| A13 | Harm reports same day to a named person, everything else in five days  | **Severe** — a promise we shouldn't be inventing        | The named person is the ask                                                                    |
