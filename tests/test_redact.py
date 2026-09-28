from vcnity.redact import next_fake, pseudonymise, redact
from vcnity.wordlist import as_hotwords, load_wordlist, person_names


def test_redact_pii():
    t = "Ring Priya on 0412 345 678 or priya@example.com at 12 Nicholas Street tomorrow"
    out = redact(t, names=["Priya"])
    assert "0412" not in out
    assert "example.com" not in out
    assert "Nicholas Street" not in out
    assert "Priya" not in out and "priya" not in out
    assert out.count("[name]") == 1
    assert "tomorrow" in out


def test_redact_leaves_clean_text_alone():
    t = "The carpark near the river needs better lighting"
    assert redact(t, names=["Priya"]) == t


def test_wordlist(tmp_path):
    p = tmp_path / "w.txt"
    p.write_text("# comment\nKelvin Grove\nPriya @person\n\nKelvin Grove\nIpswich\n", encoding="utf-8")
    assert load_wordlist(p) == ["Kelvin Grove", "Priya", "Ipswich"]
    assert person_names(p) == ["Priya"]
    assert as_hotwords(load_wordlist(p)) == "Kelvin Grove, Priya, Ipswich"


def test_wordlist_missing_file(tmp_path):
    assert load_wordlist(tmp_path / "nope.txt") == []


def test_pseudonymise_swaps_names_and_strips_details():
    out = pseudonymise("Priya told PRIYA's friend Tom: ring 0412 345 678", {"Priya": "Alex", "Tom": "Sam"})
    assert out == "Alex told Alex's friend Sam: ring [phone]"


def test_next_fake_skips_real_names_and_taken_ones():
    assert next_fake(set(), {"Priya"}) == "Alex"
    assert next_fake({"Alex"}, {"Sam"}) == "Jordan"       # Alex taken, Sam is a real person in the job
