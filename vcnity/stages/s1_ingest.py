"""Stage 1 — Ingest. Converts formats and records where each file came from.

    audio  → 16 kHz mono WAV (PyAV; no system ffmpeg needed)
    image  → EXIF-stripped JPEG copy (GPS and device data never travel further)
    text   → plain text; pictures inside slides become image files of their own
    brief  → the "Background" cells of the client's spreadsheet, into Job.brief

No AI runs here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from ..models import ConsentRecord, Job, SourceFile
from .s0_intake import sha256_of

# ---------- audio ----------


def audio_to_wav16k(src: Path, dst: Path) -> Path:
    import av

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    with av.open(str(src)) as inp, av.open(str(dst), "w") as out:
        ostream = out.add_stream("pcm_s16le", rate=16000)
        ostream.layout = "mono"
        for frame in inp.decode(audio=0):
            for rf in resampler.resample(frame):
                for pkt in ostream.encode(rf):
                    out.mux(pkt)
        for rf in resampler.resample(None):
            for pkt in ostream.encode(rf):
                out.mux(pkt)
        for pkt in ostream.encode(None):
            out.mux(pkt)
    return dst


def audio_duration_s(path: Path) -> float:
    import av

    with av.open(str(path)) as c:
        return float(c.duration / 1e6) if c.duration else 0.0


# ---------- images ----------


def strip_exif(src: Path, dst: Path) -> tuple[Path, int, int]:
    from PIL import Image, ImageOps

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # bake orientation in, then drop the tag
        im = im.convert("RGB")
        im.save(dst, format="JPEG", quality=95)  # no exif= → none written
        return dst, im.width, im.height


# ---------- text ----------


def _docx_text(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _pptx_text(path: Path, out_dir: Path | None) -> tuple[str, list[Path]]:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    parts: list[str] = []
    images: list[Path] = []
    stem = Path(path).stem
    for si, slide in enumerate(prs.slides, start=1):
        parts.append(f"[slide {si}]")
        for mi, shape in enumerate(slide.shapes, start=1):
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                ext = shape.image.ext or "png"
                p = out_dir / f"{stem}_slide{si}_{mi}.{ext}"
                p.write_bytes(shape.image.blob)
                images.append(p)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            parts.append("[notes] " + slide.notes_slide.notes_text_frame.text.strip())
    return "\n".join(parts), images


def extract_text(path: Path, out_dir: Path | None = None) -> tuple[str, list[Path]]:
    """Plain text from docx / pptx / txt / md, plus any pictures found inside."""
    path = Path(path)
    suf = path.suffix.lower()
    if suf == ".docx":
        return _docx_text(path), []
    if suf == ".pptx":
        return _pptx_text(path, out_dir)
    if suf in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace"), []
    raise ValueError(f"not a text file: {path}")


# ---------- brief ----------


def brief_from_xlsx(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return ""
    header = [str(h).strip().lower() if h else "" for h in rows[0]]
    col = header.index("background") if "background" in header else (1 if len(header) > 1 else 0)
    title_col = 0 if col != 0 else None
    parts = []
    for r in rows[1:]:
        if r is None or col >= len(r) or not r[col]:
            continue
        title = f"{r[title_col]}: " if title_col is not None and r[title_col] else ""
        parts.append(f"{title}{str(r[col]).strip()}")
    return "\n\n".join(parts)


# ---------- the stage ----------


def run(session, job_id: int, cache_dir: Path | None = None) -> list[dict]:
    cache = Path(cache_dir or settings.cache_dir) / "ingest"
    cache.mkdir(parents=True, exist_ok=True)
    job = session.get(Job, job_id)
    results: list[dict] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for sf in list(session.query(SourceFile).filter_by(job_id=job_id).all()):
        if sf.provenance and sf.provenance.get("ingested_path"):
            results.append({"file_id": sf.id, "kind": sf.kind, **sf.provenance, "cached": True})
            continue
        src = Path(sf.path)
        prov: dict = {"source": str(src), "sha256": sf.sha256, "when": now}
        if sf.kind == "audio":
            dst = audio_to_wav16k(src, cache / f"{sf.sha256}.wav")
            prov.update(ingested_path=str(dst), duration_s=round(audio_duration_s(dst), 1), tool="pyav→16k mono")
        elif sf.kind == "image":
            dst, w, h = strip_exif(src, cache / f"{sf.sha256}.jpg")
            prov.update(ingested_path=str(dst), width=w, height=h, tool="pillow exif-strip")
        elif sf.kind == "text":
            text, pics = extract_text(src, out_dir=cache / f"{sf.sha256}_pics")
            dst = cache / f"{sf.sha256}.txt"
            dst.write_text(text, encoding="utf-8")
            prov.update(ingested_path=str(dst), chars=len(text), tool=f"python-{src.suffix[1:]}")
            for pic in pics:  # pictures inside slides are artefacts in their own right
                child = SourceFile(
                    job_id=job_id, filename=pic.name, kind="image", level=sf.level,
                    level_confirmed_by_community=sf.level_confirmed_by_community,
                    consent_id=sf.consent_id, sha256=sha256_of(pic), path=str(pic),
                    provenance={"source": str(src), "embedded_in": sf.filename, "when": now},
                )
                session.add(child)
        elif sf.kind == "brief":
            text = brief_from_xlsx(src)
            job.brief = (job.brief + "\n\n" + text).strip() if job.brief else text
            prov.update(ingested_path=str(src), chars=len(text), tool="openpyxl")
        sf.provenance = prov
        results.append({"file_id": sf.id, "kind": sf.kind, **prov})
    job.status = "stage1:done"
    session.flush()
    return results
