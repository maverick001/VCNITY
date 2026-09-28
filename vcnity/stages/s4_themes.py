"""Stage 4 — Draft themes. Sorts related bits into the themes agreed with the
community at stage 1, each linked to its quotes, and suggests new *draft* themes
for anything that doesn't fit (PRD §4 stage 4, A17).

Level 2 first: real names are swapped for made-up ones, and a person checks the
swap before any Level 2 material is sorted. Until then this stage builds the
units, finds the names, and stops.

How traceability is guaranteed: the model never writes a quote. Units (bits of
material) are embedded; each is sorted into the nearest agreed theme, or
clustered with the rest. A theme's quotes ARE its members. The model only puts a
label and a summary on a new cluster, from those quotes alone. A fabricated
quote is structurally impossible; a summary that says more than the quotes is
caught at stage 5.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from ..config import settings
from ..models import Artefact, Job, Pseudonym, Segment, SourceFile, Theme, ThemeQuote, Unit
from ..providers import router
from ..redact import next_fake, pseudonymise
from ..wordlist import person_names
from ._gate import ai_allowed

log = logging.getLogger(__name__)
EMBED_MODEL = "paraphrase-multilingual-mpnet-base-v2"
MIN_WORDS = 6
NAME_SCAN_CHARS = 6000  # text per name-scan call; a 4B model loses track beyond this
_embedder = None

SYSTEM = (
    "You label groups of quotes from a community co-design session. "
    "You may only restate what the quotes say. Never add facts, causes, or judgements. "
    "Plain English, short sentences."
)
PROMPT = (
    "Here are quotes that a clustering step grouped together:\n\n{quotes}\n\n"
    "Return JSON with two keys: \"label\" (at most 6 words naming what these quotes have in common) "
    "and \"summary\" (one or two sentences that only restate what the quotes say, nothing more)."
)
NAME_SYSTEM = "You find the names of real people in text. Answer only from the text."
NAME_PROMPT = (
    "TEXT:\n{text}\n\nList every first name, surname or full name of a real person in the TEXT, exactly as "
    "written. Not places, organisations or groups. Return JSON: {{\"names\": [\"...\"]}}."
)


# ---------- units ----------


def _speaker_key(sf: SourceFile, speaker: str | None) -> str:
    return f"{sf.id}:{speaker or 'unk'}" if sf.kind == "audio" else f"file:{sf.id}"


def _rows_for(session, sf: SourceFile) -> list[tuple[str, int, str, str | None]]:
    """(source_type, source_id, text, speaker) for every quotable bit of one file."""
    rows: list[tuple[str, int, str, str | None]] = []
    if sf.kind == "audio":
        for seg in session.query(Segment).filter_by(file_id=sf.id, variant="with_wordlist").order_by(Segment.start_s):
            if len(seg.text.split()) >= MIN_WORDS:
                rows.append(("segment", seg.id, seg.text, seg.speaker))
    elif sf.kind == "image":
        art = session.query(Artefact).filter_by(file_id=sf.id).one_or_none()
        if art and art.verbatim_text.strip():
            lines = [ln.strip() for ln in art.verbatim_text.splitlines() if ln.strip()]
            text = " / ".join(lines)
            if art.maker_statement.strip():
                text += f"\nMaker says: {art.maker_statement.strip()}"
            rows.append(("artefact", art.id, text, None))
    elif sf.kind == "text":
        path = sf.provenance.get("ingested_path")
        if path:
            for i, para in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").split("\n")):
                if len(para.split()) >= MIN_WORDS:
                    rows.append(("text", i, para.strip(), None))
    return rows


def name_map(session, job_id: int) -> dict[str, str]:
    return {p.real: p.fake for p in session.query(Pseudonym).filter_by(job_id=job_id).all()}


def add_name(session, job_id: int, real: str, source: str) -> Pseudonym | None:
    """Give a real name its made-up name, unless it already has one."""
    real = real.strip()
    if not real:
        return None
    existing = session.query(Pseudonym).filter_by(job_id=job_id).all()
    if any(p.real.lower() == real.lower() for p in existing):
        return None
    reals = {p.real for p in existing} | {real}
    p = Pseudonym(job_id=job_id, real=real, fake=next_fake({p.fake for p in existing}, reals), source=source)
    session.add(p)
    session.flush()
    return p


def scan_names(session, job_id: int) -> int:
    """Word-list names, then the local model's, for every Level 2 file not scanned yet.

    A name the model returns counts only if it is really in the text — a model
    that invents a name does no harm, it just gets ignored.
    """
    added = 0
    for n in person_names(settings.wordlist_path):
        added += add_name(session, job_id, n, "wordlist") is not None
    for sf in session.query(SourceFile).filter_by(job_id=job_id, level=2).all():
        if not ai_allowed(sf) or (sf.provenance or {}).get("names_scanned"):
            continue
        text = "\n".join(t for _, _, t, _ in _rows_for(session, sf))
        for start in range(0, len(text), NAME_SCAN_CHARS):
            chunk = text[start:start + NAME_SCAN_CHARS]
            raw = router.call(session, job_id=job_id, stage=4, level=2, purpose="name-scan-l2-local",
                              prompt=NAME_PROMPT.format(text=chunk), system=NAME_SYSTEM,
                              json_mode=True, name_scan=True)
            try:
                names = json.loads(raw).get("names", [])
            except (json.JSONDecodeError, AttributeError):
                names = []
            for n in names:
                if isinstance(n, str) and n.strip() and n.strip().lower() in chunk.lower():
                    added += add_name(session, job_id, n, "model") is not None
        sf.provenance = {**(sf.provenance or {}), "names_scanned": True}
    session.flush()
    return added


def apply_names(session, job_id: int) -> None:
    """Re-swap every Level 2 unit's names after the name list changed."""
    mapping = name_map(session, job_id)
    for u in session.query(Unit).filter_by(job_id=job_id, level=2).all():
        u.redacted_text = pseudonymise(u.text, mapping)
    session.flush()


def build_units(session, job_id: int) -> int:
    """(Re)build the quotable units for a job from canonical segments, artefacts and text files.

    Units are updated in place, not deleted and remade: signed-off themes keep
    their quotes across a re-run. A unit whose material has gone is deleted, or
    excluded if a theme still points at it.
    """
    mapping = name_map(session, job_id)
    existing = {(u.file_id, u.source_type, u.source_id): u for u in session.query(Unit).filter_by(job_id=job_id)}
    seen: set[tuple[int, str, int]] = set()
    n = 0
    for sf in session.query(SourceFile).filter_by(job_id=job_id).all():
        if sf.kind == "brief" or not ai_allowed(sf):
            continue
        for source_type, source_id, text, speaker in _rows_for(session, sf):
            key = (sf.id, source_type, source_id)
            seen.add(key)
            redacted = pseudonymise(text, mapping) if sf.level == 2 else text
            u = existing.get(key)
            if u is None:
                session.add(Unit(job_id=job_id, file_id=sf.id, source_type=source_type, source_id=source_id,
                                 text=text, redacted_text=redacted, speaker_key=_speaker_key(sf, speaker),
                                 level=sf.level))
            else:
                u.text, u.redacted_text, u.level = text, redacted, sf.level
                u.speaker_key, u.excluded = _speaker_key(sf, speaker), False
            n += 1
    quoted = {uid for (uid,) in session.query(ThemeQuote.unit_id).join(Unit).filter(Unit.job_id == job_id)}
    for key, u in existing.items():
        if key not in seen:
            if u.id in quoted:
                u.excluded = True
            else:
                session.delete(u)
    session.flush()
    return n


def waiting_name_check(session, job_id: int) -> list[str]:
    """Level 2 files with material whose made-up names nobody has checked yet."""
    files = session.query(SourceFile).filter_by(job_id=job_id, level=2).all()
    with_units = {fid for (fid,) in session.query(Unit.file_id).filter_by(job_id=job_id, level=2).distinct()}
    return [f.filename for f in files if f.id in with_units and not f.names_checked]


def set_names_checked(session, file_id: int) -> SourceFile:
    sf = session.get(SourceFile, file_id)
    if sf is None:
        raise KeyError(file_id)
    if sf.level != 2:
        raise ValueError("only Level 2 files have names swapped")
    sf.names_checked = True
    session.flush()
    return sf


def names_changed(session, job_id: int) -> None:
    """The name list changed: re-swap, and every Level 2 file needs checking again."""
    apply_names(session, job_id)
    for sf in session.query(SourceFile).filter_by(job_id=job_id, level=2).all():
        sf.names_checked = False
    session.flush()


# ---------- embed + cluster ----------


def embed(texts: list[str]) -> np.ndarray:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBED_MODEL, cache_folder=str(settings.cache_dir / "models"))
    return np.asarray(_embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False))


def _agglomerative(X: np.ndarray, min_size: int) -> list[int]:
    from sklearn.cluster import AgglomerativeClustering

    if len(X) < 2:
        return [0] * len(X)
    model = AgglomerativeClustering(n_clusters=None, distance_threshold=0.5, metric="cosine", linkage="average")
    labels = model.fit_predict(X)
    # clusters smaller than min_size become outliers (-1), like HDBSCAN would do
    counts = {int(l): int((labels == l).sum()) for l in set(labels)}
    return [int(l) if counts[int(l)] >= min_size else -1 for l in labels]


def cluster(X: np.ndarray, min_size: int) -> list[int]:
    """Cluster ids per row; -1 means 'in no theme'. BERTopic first, agglomerative fallback."""
    X = np.asarray(X)
    if len(X) >= max(10, 3 * min_size):
        try:
            from bertopic import BERTopic
            from hdbscan import HDBSCAN
            from umap import UMAP

            umap_model = UMAP(n_neighbors=min(15, len(X) - 1), n_components=min(5, len(X) - 2),
                              min_dist=0.0, metric="cosine", random_state=42)
            hdb = HDBSCAN(min_cluster_size=min_size, metric="euclidean", prediction_data=False)
            topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdb, calculate_probabilities=False, verbose=False)
            docs = [f"doc {i}" for i in range(len(X))]
            topics, _ = topic_model.fit_transform(docs, embeddings=X)
            labels = [int(t) for t in topics]
            if len({l for l in labels if l >= 0}) >= 2:
                return labels
            log.info("BERTopic found <2 topics; falling back to agglomerative clustering")
        except Exception as e:  # pragma: no cover - depends on environment
            log.warning("BERTopic failed (%s); falling back to agglomerative clustering", e)
    return _agglomerative(X, min_size)


def sort_into(X: np.ndarray, A: np.ndarray, threshold: float) -> list[int]:
    """Index of the nearest agreed theme per row, or -1 if none is close enough. Rows are unit-normalised."""
    if len(A) == 0 or len(X) == 0:
        return [-1] * len(X)
    sims = np.asarray(X) @ np.asarray(A).T
    best = sims.argmax(axis=1)
    return [int(b) if sims[i, b] >= threshold else -1 for i, b in enumerate(best)]


# ---------- label ----------


def label_cluster(session, job_id: int, level: int, quotes: list[str]) -> dict:
    raw = router.call(
        session, job_id=job_id, stage=4, level=level, purpose="theme-label",
        prompt=PROMPT.format(quotes="\n".join(f"- {q}" for q in quotes)), system=SYSTEM,
        json_mode=True, redacted=True,
    )
    try:
        data = json.loads(raw)
        return {"label": str(data.get("label", "")).strip()[:200] or "Untitled theme",
                "summary": str(data.get("summary", "")).strip()}
    except (json.JSONDecodeError, AttributeError):
        return {"label": "Untitled theme", "summary": raw.strip()[:500]}


# ---------- the stage ----------


def run(session, job_id: int, min_size: int | None = None) -> dict:
    min_size = min_size or max(2, settings.small_n - 1)
    job = session.get(Job, job_id)
    n_units = build_units(session, job_id)
    names_found = scan_names(session, job_id)
    apply_names(session, job_id)
    waiting = waiting_name_check(session, job_id)
    if waiting:
        job.status = "stage4:waiting-names"
        session.flush()
        return {"units": n_units, "names_found": names_found, "waiting_name_check": waiting,
                "note": "A person must check the made-up names on these Level 2 files before sorting starts."}

    # Community-decided themes survive a re-run ("have the fix stick"); drafts don't.
    for t in session.query(Theme).filter(Theme.job_id == job_id, Theme.status.in_(("draft", "unsupported"))).all():
        session.delete(t)
    agreed = (session.query(Theme).filter(Theme.job_id == job_id, Theme.agreed_upfront.is_(True),
                                          Theme.status.notin_(("rejected", "cut"))).order_by(Theme.id).all())
    for t in agreed:  # agreed themes are re-sorted from scratch every run
        session.query(ThemeQuote).filter_by(theme_id=t.id).delete(synchronize_session=False)
    session.flush()
    held = {uid for (uid,) in session.query(ThemeQuote.unit_id).join(Theme).filter(Theme.job_id == job_id)}
    units = [u for u in session.query(Unit).filter_by(job_id=job_id, excluded=False).order_by(Unit.id).all()
             if u.id not in held]
    if not units:
        job.status = "stage4:done"
        session.flush()
        return {"units": n_units, "sorted": 0, "themes": 0}

    X = embed([u.redacted_text for u in units])
    for u, vec in zip(units, X):
        u.embedding = vec.tolist()
    A = embed([f"{t.label}. {t.summary}".strip() for t in agreed]) if agreed else np.zeros((0, X.shape[1]))
    targets = sort_into(X, A, settings.sort_similarity)

    sorted_n = 0
    for u, ti in zip(units, targets):
        if ti >= 0:
            session.add(ThemeQuote(theme_id=agreed[ti].id, unit_id=u.id))
            sorted_n += 1
    session.flush()
    for t in agreed:
        members = [tq.unit for tq in session.query(ThemeQuote).filter_by(theme_id=t.id).all()]
        t.n_people = len({m.speaker_key for m in members})
        t.level = max([t.level] + [m.level for m in members])  # levels only go up

    rest = [(u, x) for u, x, ti in zip(units, X, targets) if ti < 0]
    made = 0
    groups: dict[int, list[Unit]] = {}
    if rest:
        labels = cluster(np.asarray([x for _, x in rest]), min_size)
        for (u, _), l in zip(rest, labels):
            if l >= 0:
                groups.setdefault(l, []).append(u)
        for cid, members in sorted(groups.items()):
            level = max(m.level for m in members)
            lab = label_cluster(session, job_id, level, [m.redacted_text for m in members])
            theme = Theme(job_id=job_id, label=lab["label"], summary=lab["summary"], status="draft",
                          cluster_id=cid, level=level, n_people=len({m.speaker_key for m in members}))
            session.add(theme)
            session.flush()
            for m in members:
                session.add(ThemeQuote(theme_id=theme.id, unit_id=m.id))
            made += 1
    job.status = "stage4:done"
    session.flush()
    return {"units": n_units, "names_found": names_found, "sorted": sorted_n, "themes": made,
            "outliers": len(rest) - sum(len(g) for g in groups.values())}
