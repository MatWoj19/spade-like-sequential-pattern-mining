from pathlib import Path
import csv
import re

import pytest

from spade_like.core import (
    SequenceDatabase,
    d_spade,
    b_spade,
    max_length_d_spade,
    max_length_b_spade,
    pattern_length,
    pattern_to_string,
    run_algorithm,
    write_results,
)

ROOT = Path(__file__).resolve().parents[1]
SMALL = ROOT / "data" / "small.txt"


def as_pairs(stats):
    return {(pattern_to_string(record.pattern), record.support) for record in stats.discovered}


def test_small_exact_patterns_and_supports():
    stats = run_algorithm("dSPADE", SMALL, 2)
    expected = {
        ("<(a)>", 4), ("<(b)>", 4), ("<(d)>", 2), ("<(f)>", 4),
        ("<(a b)>", 3), ("<(a f)>", 3), ("<(b)(a)>", 2),
        ("<(b f)>", 4), ("<(d)(a)>", 2), ("<(d)(b)>", 2),
        ("<(d)(f)>", 2), ("<(f)(a)>", 2), ("<(a b f)>", 3),
        ("<(b f)(a)>", 2), ("<(d)(b)(a)>", 2),
        ("<(d)(b f)>", 2), ("<(d)(f)(a)>", 2),
        ("<(d)(b f)(a)>", 2),
    }
    assert as_pairs(stats) == expected
    assert stats.longest_pattern == 4


def test_same_transaction_and_later_transaction_are_distinguished():
    stats = run_algorithm("dSPADE", SMALL, 1)
    records = {pattern_to_string(r.pattern): r for r in stats.discovered}
    assert records["<(d f)>"].support == 1
    assert records["<(d)(f)>"].support == 2
    assert records["<(d f)>"].tidlist_length == 1
    assert records["<(d)(f)>"].tidlist_length == 3


def test_dfs_bfs_equivalence():
    db = SequenceDatabase.read(SMALL)
    assert as_pairs(d_spade(db, 2)) == as_pairs(b_spade(db, 2))


def test_limited_dfs_bfs_equivalence_and_limit():
    db = SequenceDatabase.read(SMALL)
    dfs = max_length_d_spade(db, 2, 3)
    bfs = max_length_b_spade(db, 2, 3)
    assert as_pairs(dfs) == as_pairs(bfs)
    assert all(pattern_length(r.pattern) <= 3 for r in dfs.discovered)


def test_full_and_limited_equal_when_limit_is_sufficient():
    db = SequenceDatabase.read(SMALL)
    full_dfs = d_spade(db, 2)
    full_bfs = b_spade(db, 2)
    limited_dfs = max_length_d_spade(db, 2, 4)
    limited_bfs = max_length_b_spade(db, 2, 4)
    assert as_pairs(full_dfs) == as_pairs(full_bfs) == as_pairs(limited_dfs) == as_pairs(limited_bfs)


def test_out_and_stat_are_complete(tmp_path):
    stats = run_algorithm("dSPADE", SMALL, 2)
    out_path, stat_path = write_results(stats, tmp_path)

    with out_path.open(encoding="utf-8") as file:
        rows = list(csv.reader(file, delimiter=";"))
    assert rows[0] == [
        "długość wzorca", "liczba elementów", "długość tidlisty",
        "wsparcie sup", "wzorzec sekwencyjny",
    ]
    assert len(rows) == 19

    text = stat_path.read_text(encoding="utf-8")
    required = [
        "# wszystkich utworzonych kandydatów:",
        "suma wsparć wszystkich kandydatów:",
        "suma długości tidlist wszystkich kandydatów:",
        "# wszystkich odkrytych wzorców sekwencyjnych:",
        "suma wsparć wszystkich wzorców:",
        "suma długości tidlist wszystkich wzorców:",
        "całkowity czas bez odczytu:",
        "całkowity czas wykonania:",
        "k=5:",
    ]
    for phrase in required:
        assert phrase in text

    values = {
        key: float(value)
        for key, value in re.findall(
            r"(czas odczytu pliku wejściowego|czas wyznaczania wzorców|czas zapisywania wyników|całkowity czas bez odczytu|całkowity czas wykonania): ([0-9.]+) s",
            text,
        )
    }
    assert values["całkowity czas bez odczytu"] == pytest.approx(
        values["czas wyznaczania wzorców"] + values["czas zapisywania wyników"], abs=2e-9
    )
    assert values["całkowity czas wykonania"] == pytest.approx(
        values["czas odczytu pliku wejściowego"] + values["całkowity czas bez odczytu"], abs=2e-9
    )


def test_limited_stat_contains_zero_next_level(tmp_path):
    stats = run_algorithm("maxLength-dSPADE", SMALL, 2, 2)
    _, stat_path = write_results(stats, tmp_path)
    text = stat_path.read_text(encoding="utf-8")
    assert "k=3: kandydaci=0" in text
    assert "nie byli generowani z powodu ograniczenia maxLength" in text


def test_invalid_parameters_and_input(tmp_path):
    db = SequenceDatabase.read(SMALL)
    with pytest.raises(ValueError):
        d_spade(db, 0)
    with pytest.raises(ValueError):
        max_length_d_spade(db, 1, 0)
    bad = tmp_path / "bad.txt"
    bad.write_text("1 10\n", encoding="utf-8")
    with pytest.raises(ValueError):
        SequenceDatabase.read(bad)

def test_native_spmf_format(tmp_path):
    from spade_like.core import SequenceDatabase, d_spade, pattern_to_string
    path = tmp_path / "sample_spmf.txt"
    path.write_text("1 -1 2 -1 -2\n1 2 -1 -2\n", encoding="utf-8")
    db = SequenceDatabase.read(path)
    assert db.summary()["num_sequences"] == 2
    assert db.summary()["num_transactions"] == 3
    stats = d_spade(db, 1, str(path))
    found = {(pattern_to_string(r.pattern), r.support) for r in stats.discovered}
    assert ("<(1)>", 2) in found
    assert ("<(1)(2)>", 1) in found
    assert ("<(1 2)>", 1) in found
