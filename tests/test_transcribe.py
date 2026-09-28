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


def test_wer_against_reference():
    assert s2_transcribe.wer("the cat sat", "the cat sat") == 0.0
    assert 0 < s2_transcribe.wer("the cat sat", "the cat stood") < 1


def test_ai_allowed_gate():
    assert ai_allowed(SimpleNamespace(level=1, level_confirmed_by_community=False)) is True
    assert ai_allowed(SimpleNamespace(level=2, level_confirmed_by_community=False)) is False
    assert ai_allowed(SimpleNamespace(level=2, level_confirmed_by_community=True)) is True
    assert ai_allowed(SimpleNamespace(level=3, level_confirmed_by_community=True)) is False
