"""Stage 4 — Draft themes. Groups related bits into *draft* themes, each linked
to its quotes.

How traceability is guaranteed: the model never writes a quote. Units (bits of
material) are embedded and clustered; a theme's quotes ARE its cluster members.
The model only puts a label and a summary on a cluster, from those quotes
alone. A fabricated quote is structurally impossible; a summary that says more
than the quotes is caught at stage 5.
"""
from __future__ import annotations

import json
import logging

import numpy as np

from ..config import settings
from ..models import Artefact, Job, Segment, SourceFile, Theme, ThemeQuote, Unit
from ..providers import router
from ..redact import redact
from ..wordlist import person_names
from ._gate import ai_allowed

log = logging.getLogger(__name__)
EMBED_MODEL = "paraphrase-multilingual-mpnet-base-v2"
MIN_WORDS = 6
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


# ---------- units ----------


def _speaker_key(sf: SourceFile, speaker: str | None) -> str:
    return f"{sf.id}:{speaker or 'unk'}" if sf.kind == "audio" else f"file:{sf.id}"


def build_units(session, job_id: int) -> int:
    """(Re)build the quotable units for a job from canonical segments, artefacts and text files."""
    session.query(Unit).filter_by(job_id=job_id).delete(synchronize_session=False)
    names = person_names(settings.wordlist_path)
    n = 0
    for sf in session.query(SourceFile).filter_by(job_id=job_id).all():
        if sf.kind == "brief" or not ai_allowed(sf):
            continue
        rows: list[tuple[str, int, str, str | None]] = []  # (source_type, source_id, text, speaker)
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
                from pathlib import Path

                for i, para in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").split("\n")):
                    if len(para.split()) >= MIN_WORDS:
                        rows.append(("text", i, para.strip(), None))
        for source_type, source_id, text, speaker in rows:
            session.add(Unit(
                job_id=job_id, file_id=sf.id, source_type=source_type, source_id=source_id, text=text,
                redacted_text=redact(text, names) if sf.level == 2 else text,
                speaker_key=_speaker_key(sf, speaker), level=sf.level,
            ))
            n += 1
    session.flush()
    return n


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
    n_units = build_units(session, job_id)
    units = session.query(Unit).filter_by(job_id=job_id, excluded=False).order_by(Unit.id).all()
    # Community-decided themes survive a re-run ("have the fix stick"); drafts don't.
    for t in session.query(Theme).filter(Theme.job_id == job_id, Theme.status.in_(("draft", "unsupported"))).all():
        session.delete(t)
    session.flush()
    if not units:
        return {"units": 0, "themes": 0}

    X = embed([u.redacted_text for u in units])
    for u, vec in zip(units, X):
        u.embedding = vec.tolist()
    labels = cluster(X, min_size)
    groups: dict[int, list[Unit]] = {}
    for u, l in zip(units, labels):
        if l >= 0:
            groups.setdefault(l, []).append(u)

    made = 0
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
    job = session.get(Job, job_id)
    job.status = "stage4:done"
    session.flush()
    return {"units": n_units, "themes": made, "outliers": sum(1 for l in labels if l < 0)}
