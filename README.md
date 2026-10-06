# VCNITY Community App

This is a prototype application of AI-assisted data pipeline that turns community creative Co-Design materials, such as multi-speaker audio in several languages and accents, local slang, photos of handmade artefacts into policy-ready themes, without letting AI distort or override the community's say. Everything runs on your local PC — nothing is sent to the cloud.

The Main Dashboard:

![The prototype's Data Ingest page — every file gets a consent record and a sensitivity level before anything runs on it](images/index_page.jpg)

## Preparation for Installation

You'll need:

1. [uv](https://docs.astral.sh/uv/) installed and on your PATH.
2. [Ollama](https://ollama.com) is installed and running, with the two models below pulled. If your machine has 16GB RAM and no GPU, that's fine — the app never loads both models at once.
3. To process audio files, a free HuggingFace token needs to be configured. You need to add your token `HF_TOKEN=hf_…` to `.env`. Without it, the transcription can still work, but without speaker labels to separate them.

Pull these two open-source Qwen models from Ollama:

```
ollama pull qwen3.5:4b    # text model: finds names, labels themes, evidence checks, reports
ollama pull qwen3-vl:4b   # vision model for preprocessing image artefacts
```

## Install and run

```
git clone https://github.com/maverick001/vcnity.git
cd vcnity
cp .env.example .env    # add your Hugging Face Token to fetch the model file
python start.py         # installs dependencies, starts the database, API, and UI
```

Open http://localhost:3000 once the app is running, and sign in.

The sign-in page. Everyone signs in with an account made for them (see Accounts below), and lands on their own page:

![The sign-in page: username and password, then straight to your own page](images/auth.jpg)

### Accounts

Everyone signs in, and each role lands on its own page. There's no sign-up page: make accounts from the command line, while the app is running or not.

```
uv run python scripts/users.py demo                       # one account per role; prints passwords once
uv run python scripts/users.py add sam community --job 1  # asks for a password
uv run python scripts/users.py list
uv run python scripts/users.py password sam
```

A community or client account belongs to one job and sees only that job; `demo` ties them to the newest job, and on a fresh install with no job yet it makes only the facilitator and analyst. A facilitator or analyst account sees every job. The API checks the account on every request, so nobody can do another role's work by going around the app. A sign-in lasts 12 hours.

The first run on your PC will download about 2 GB of Python packages, plus a 3 GB speech-recognition model the first time you transcribe something, and a small multilingual embedding model (used to group material into draft themes) the first time you draft themes. None of this is stored in the project folder — it all lives in `~/.vcnity/`, so the repo itself stays small.

## Speeding up transcription (Optional)

Transcribing a recording can take about an hour on a laptop CPU. Rather than wait for that live, you can pre-run the whole pipeline ahead of time. It reads the raw files (recordings, photos, Word/PowerPoint/text files and the client's spreadsheet) from `VCNITY_DATA_DIR`, which defaults to `~/.vcnity/raw`; set it in `.env` to read them from somewhere else:

```
uv run python scripts/precompute.py --confirm-levels --demo-signoff
```

This does two things: `--confirm-levels` confirms each file's sensitivity level for you (normally a community reviewer's job, and AI stages won't run without it), and `--demo-signoff` fills in the person steps with clearly-labelled placeholder decisions: the Level 2 name check before draft themes, sign-off, attendance and people counts, identifiability, and the reports. The result: every page in the app has something to look at, without anyone having done that review for real yet.

Once you're ready to do that review for real, clear the placeholders first:

```
uv run python scripts/precompute.py --job 1 --reset-signoff
```

To start a job over completely, the analyst uses **Reset job** at the bottom of the Data Pipeline page. It removes everything the stages produced but keeps your uploaded files with their consent and levels; you then run the stages again from 1.

## Running the tests

```
uv run pytest tests -q
```

A full run (112 tests) takes about 2–3 minutes. Don't start a second run while one is going: every run starts its own database in `~/.vcnity/test` and wipes it first, so two at once break each other with setup errors that have nothing to do with the code.

## Using the app

Sign in and you land on your own page; **Sign out** is at the top right. Each step below says which role does it. The sidebar (facilitator and analyst only) lists the stages 1–8 in order; a green tick means that stage has output, and an amber person icon means it's waiting for someone (hover to see what for). You run a stage with **Run** on the **Data Pipeline** page, or the re-run button on that stage's own page — only the analyst can. The facilitator sees the stage pages but doesn't run stages, reset a job, or see the made-up names list, the identifiability flags or the claims the evidence check threw out.

The **community** and the **client** don't see the sidebar or the stage pages. Signing in as either takes you to a page of their own. The community page (`/community`) is one plain-language page with everything a community reviewer does: check each file's label (with a preview of the file), agree themes and the word list, say what each made thing means, sign off the themes, and approve the report. It shows only the quotes behind each theme, plus a search when adding one we missed — never a full transcript. The client page (`/client`) shows the report once both approvals are in, and nothing else.

A job, step by step:

1. **Data Ingest** (facilitator and community, *1 · Data Ingest*).
   - **Upload** (facilitator). Create a job, then upload recordings, photos, Word/PowerPoint/text files and the client's spreadsheet. Every file needs a consent label and a sensitivity level — the Levels table on the page says which is which. If you're not sure, go up a level.
   - **Who came** (facilitator). Enter how many people came to each session. The total is the "of M" in the report's "N of M participants".
   - **Confirm levels and agree themes** (community, on the community page under *Check the labels* and *Our words*). Confirm the level of every Level 2 file — no AI runs on it until you do. Add the themes you want the material sorted into.
   - Then press **Run** on stage 1 in Data Pipeline to convert the files. No AI runs here. Transcription and theme drafting only read the converted files, so don't skip this even if there's no audio.
2. **Word list and transcripts** (anyone, *2 · Audio Processing*). Add names, slang and local place words to the word list; put `@person` after a person's name. Run stage 2. If a recording comes back with no speakers identified (every line shows "?"), an amber warning says so; the analyst can re-run stage 2 to try again, and speaker labels need the HuggingFace token from the install steps. To measure what the word list did, paste a hand-corrected transcript and press **Compute WER**.
3. **Things people made** (anyone, *3 · Image Processing*). Run stage 3, then type in what each maker said their piece means. The AI never guesses that.
4. **Check names, then sort** (analyst, *4 · Draft themes*). Run stage 4. If there is Level 2 material it stops: read what sorting will see, add any real name that slipped through, remove anything that isn't a name, and press **Names are right** on each file. Run stage 4 again to sort.
5. **Check the evidence** (anyone, *5 · Evidence check* — same page as stage 4). Run stage 5. Any theme that claims something its quotes don't say is marked *unsupported* and never reaches sign-off.
6. **Sign off** (community, *What we heard* on the community page). Confirm, fix or reject each theme. Add any theme we missed — switch on *This comes from Restricted material* for one that comes from material only people have seen; it reaches the client with no quotes.
7. **Count and check** (analyst, *7 · Security Check*). Type the number of people behind each theme, run stage 7, then decide every flag — keep or cut — and write down why.
8. **Report** (community and analyst, *8 · Reporting*; the community approves under *The report* on their page). Run stage 8. The community and the analyst both approve, then export it as a Word file.

**Chat with Data** (facilitator or analyst, the violet button top right on any page). Opens a chat in its own browser tab where you can ask about the current job's material — "where did people talk about parking?", "what did the second recording say about the carpark?". A local model answers only from the material below Level 3 and lists the passages it used; Level 2 names may show as made-up stand-ins. It won't say what anything means — that's the community's call at sign-off. Answers can take up to a minute, the chat is blocked while a stage is running, and nothing is kept after you reload the page.

**Model Configuration** (analyst only, *Model Configuration* at the bottom of the sidebar). The Hugging Face, Ollama and Kaggle logos beside the heading are decoration; they show where local models come from. Pick which model each step uses for the current job: audio processing, image processing, draft themes, evidence check, security check and reporting. Each model shows its parameter count, where it came from and its size on disk, e.g. `faster-whisper-large-v3 (1.55B) · Systran · 3.1 GB`. Only models already on this laptop are listed — speech models in `~/.vcnity/cache/models`, text and vision models from Ollama. A model you `ollama pull` shows up the next time you open or reload the page, no code change; Ollama says whether it reads images, which decides the steps it's offered for. A new speech model gets downloaded the first time stage 2 runs with it set as `VCNITY_ASR_MODEL` in `.env`. A pick applies to that job only; anything a step has already made stays until you re-run it. Without a pick, a step uses the defaults in `.env`. Nobody else sees the page or which models are in use.
