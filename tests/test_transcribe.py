from types import SimpleNamespace

from vcnity.models import Job, Segment, SourceFile
from vcnity.stages import s2_transcribe, s2b_diarise
from vcnity.stages._gate import ai_allowed


def test_unsure_threshold_is_prd_confidence():
    import math

    assert math.isclose(math.exp(s2_transcribe.UNSURE_LOGPROB), 0.6)     # PRD A5
    assert s2_transcribe.flag_unsure({"avg_logprob": math.log(0.59), "no_speech_prob": 0.1}) is True
    assert s2_transcribe.flag_unsure({"avg_logprob": math.log(0.61), "no_speech_prob": 0.1}) is False


def test_wordlist_term_hits():
    ref = "We met Priya at Kelvin Grove, then Priya left for Ipswich"
    out = s2_transcribe.term_hits(ref, "we met prier at kelvin grove then Priya left for Ipswich",
                                  ["Priya", "Kelvin Grove", "Ipswich", "Toowoomba"])
    assert out == {"in_reference": 4, "found": 3, "error_rate": 0.25}
    assert s2_transcribe.term_hits("nothing listed here", "x", ["Priya"])["error_rate"] is None


def test_flag_unsure():
    assert s2_transcribe.flag_unsure({"avg_logprob": -0.9, "no_speech_prob": 0.1}) is True
    assert s2_transcribe.flag_unsure({"avg_logprob": -0.3, "no_speech_prob": 0.1}) is False
    assert s2_transcribe.flag_unsure({"avg_logprob": -0.3, "no_speech_prob": 0.7}) is True


def test_load_wav_gives_pyannote_a_waveform(tmp_path):
    import struct
    import wave

    p = tmp_path / "a.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<3h", 0, 16384, -32768))
    out = s2b_diarise._load_wav(p)
    assert out["sample_rate"] == 16000
    assert tuple(out["waveform"].shape) == (1, 3)   # (channel, time), what pyannote expects
    assert out["waveform"].tolist() == [[0.0, 0.5, -1.0]]


def test_merge_speakers_by_overlap():
    segs = [SimpleNamespace(start_s=0.0, end_s=2.0, speaker=None),
            SimpleNamespace(start_s=2.5, end_s=4.0, speaker=None),
            SimpleNamespace(start_s=9.0, end_s=10.0, speaker=None)]
    turns = [(0.0, 1.5, "SPEAKER_00"), (1.5, 3.0, "SPEAKER_01"), (3.0, 5.0, "SPEAKER_00")]
    s2b_diarise.merge_speakers(segs, turns)
    assert segs[0].speaker == "SPEAKER_00"   # 1.5 s overlap beats 0.5 s
    assert segs[1].speaker == "SPEAKER_00"   # 1.0 s vs 0.5 s
    assert segs[2].speaker is None           # no overlap at all


def test_compare_variants(db_session):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=1, path="x", sha256="0" * 64)
    db_session.add(f); db_session.flush()
    db_session.add_all([
        Segment(file_id=f.id, variant="without", start_s=0, end_s=1, text="we met at kelvin grave today"),
        Segment(file_id=f.id, variant="with_wordlist", start_s=0, end_s=1, text="we met at Kelvin Grove today"),
    ])
    db_session.flush()
    out = s2_transcribe.compare(db_session, f.id)
    assert 0 < out["wer_between_runs"] < 1
    ref = s2_transcribe.compare(db_session, f.id, reference="we met at Kelvin Grove today", terms=["Kelvin Grove"])
    assert ref["wordlist_terms_with"]["error_rate"] == 0.0 and ref["wordlist_terms_without"]["error_rate"] == 1.0
    assert any(d["kind"] == "changed" for d in out["diff"])
    assert out["words_changed"] >= 1


def test_compare_ignores_capitals_and_punctuation(db_session):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=1, path="x", sha256="0" * 64)
    db_session.add(f); db_session.flush()
    db_session.add_all([
        Segment(file_id=f.id, variant="without", start_s=0, end_s=1, text="so we have codes which feel vague"),
        Segment(file_id=f.id, variant="with_wordlist", start_s=0, end_s=1, text="So, we have codes, which feel vague."),
    ])
    db_session.flush()
    out = s2_transcribe.compare(db_session, f.id)
    assert out["words_changed"] == 0 and out["wer_between_runs"] == 0.0
    assert all(d["kind"] == "same" for d in out["diff"])


def test_wer_against_reference():
    assert s2_transcribe.wer("the cat sat", "the cat sat") == 0.0
    assert 0 < s2_transcribe.wer("the cat sat", "the cat stood") < 1


def test_ai_allowed_gate():
    assert ai_allowed(SimpleNamespace(level=1, level_confirmed_by_community=False)) is True
    assert ai_allowed(SimpleNamespace(level=2, level_confirmed_by_community=False)) is False
    assert ai_allowed(SimpleNamespace(level=2, level_confirmed_by_community=True)) is True
    assert ai_allowed(SimpleNamespace(level=3, level_confirmed_by_community=True)) is False


def test_stage_2b_uses_the_speaker_model_the_job_picked(db_session, monkeypatch, tmp_path):
    from vcnity import model_choice

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    job = Job(name="speakers"); db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=1, path="x", sha256="0" * 64,
                   provenance={"ingested_path": str(wav)})
    db_session.add(f); db_session.flush()
    db_session.add(Segment(file_id=f.id, variant="with_wordlist", start_s=0, end_s=2, text="hi"))
    db_session.flush()
    used = []
    monkeypatch.setattr(s2b_diarise, "diarise", lambda w, name: used.append(name) or [(0.0, 2.0, "SPEAKER_00")])
    monkeypatch.setattr(s2b_diarise, "ai_allowed", lambda sf: True)
    monkeypatch.setattr(model_choice, "available", lambda: {"diarise": [{"name": "pyannote/speaker-diarization-community-1"}]})

    assert s2b_diarise.run(db_session, job.id)["model"] == "pyannote/speaker-diarization-3.1"   # no pick: default
    model_choice.set_choices(db_session, job.id, {"2b": "pyannote/speaker-diarization-community-1"})
    report = s2b_diarise.run(db_session, job.id)
    assert used == ["pyannote/speaker-diarization-3.1", "pyannote/speaker-diarization-community-1"]
    assert report["model"] == "pyannote/speaker-diarization-community-1"
