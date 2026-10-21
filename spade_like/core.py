from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple
import csv
import statistics

Item = str
Itemset = Tuple[Item, ...]
Pattern = Tuple[Itemset, ...]
IdList = Dict[int, Set[int]]  # CId -> indeksy transakcji, w których wzorzec może się kończyć


def pattern_length(pattern: Pattern) -> int:
    """Liczba pozycji we wzorcu, z uwzględnieniem powtórzeń."""
    return sum(len(itemset) for itemset in pattern)


def pattern_to_string(pattern: Pattern) -> str:
    return "<" + "".join("(" + " ".join(itemset) + ")" for itemset in pattern) + ">"


@dataclass
class Record:
    pattern: Pattern
    idlist: IdList

    @property
    def support(self) -> int:
        return len(self.idlist)

    @property
    def tidlist_length(self) -> int:
        return sum(len(tids) for tids in self.idlist.values())


@dataclass
class LevelStats:
    candidates: int = 0
    candidate_support_sum: int = 0
    candidate_tidlist_sum: int = 0
    patterns: int = 0
    pattern_support_sum: int = 0
    pattern_tidlist_sum: int = 0


@dataclass
class MiningStats:
    algorithm: str
    input_file: str
    min_sup: int
    max_length: Optional[int]
    read_time: float = 0.0
    mining_time: float = 0.0
    write_time: float = 0.0
    total_without_read: float = 0.0
    total_time: float = 0.0
    longest_candidate: int = 0
    longest_pattern: int = 0
    by_length: Dict[int, LevelStats] = field(default_factory=lambda: defaultdict(LevelStats))
    discovered: List[Record] = field(default_factory=list)
    dataset_summary: Dict[str, float] = field(default_factory=dict)


class SequenceDatabase:
    def __init__(self, sequences: Dict[int, List[Tuple[int, FrozenSet[Item]]]]):
        self.sequences = sequences
        self.items = sorted({item for seq in sequences.values() for _, trans in seq for item in trans})
        self.item_occ: Dict[Item, IdList] = {item: defaultdict(set) for item in self.items}
        for sid, seq in sequences.items():
            for tidx, (_, trans) in enumerate(seq):
                for item in trans:
                    self.item_occ[item][sid].add(tidx)

    @classmethod
    def read(cls, path: str | Path) -> "SequenceDatabase":
        """Czyta format wierszowy CId TId item... albo natywny format SPMF.

        Format SPMF: -1 kończy itemset/transakcję, a -2 kończy sekwencję.
        Format jest wykrywany automatycznie na podstawie pierwszego wiersza danych.
        """
        data_lines: List[Tuple[int, str]] = []
        with open(path, encoding="utf-8") as file:
            for line_no, raw in enumerate(file, 1):
                line = raw.strip()
                if line and not line.startswith(("#", "%", "@")):
                    data_lines.append((line_no, line))
        if not data_lines:
            raise ValueError("Plik wejściowy nie zawiera żadnej sekwencji danych")

        first_tokens = data_lines[0][1].replace(",", " ").split()
        is_spmf = "-1" in first_tokens or "-2" in first_tokens
        sequences: Dict[int, List[Tuple[int, FrozenSet[Item]]]] = defaultdict(list)

        if is_spmf:
            sid = 0
            for line_no, line in data_lines:
                sid += 1
                tokens = line.split()
                current: List[Item] = []
                tid = 0
                ended = False
                for token in tokens:
                    if token == "-1":
                        if not current:
                            raise ValueError(f"Pusty itemset w wierszu SPMF {line_no}")
                        tid += 1
                        sequences[sid].append((tid, frozenset(current)))
                        current = []
                    elif token == "-2":
                        if current:
                            tid += 1
                            sequences[sid].append((tid, frozenset(current)))
                            current = []
                        ended = True
                        break
                    else:
                        current.append(token)
                if not ended:
                    raise ValueError(f"Brak znacznika -2 w wierszu SPMF {line_no}")
                if not sequences[sid]:
                    raise ValueError(f"Pusta sekwencja w wierszu SPMF {line_no}")
        else:
            for line_no, line in data_lines:
                parts = line.replace(",", " ").split()
                if len(parts) < 3:
                    raise ValueError(f"Niepoprawny wiersz {line_no}: {line!r}")
                sid, tid = int(parts[0]), int(parts[1])
                items = frozenset(parts[2:])
                if not items:
                    raise ValueError(f"Transakcja w wierszu {line_no} nie zawiera pozycji")
                sequences[sid].append((tid, items))
            for sid in sequences:
                sequences[sid].sort(key=lambda row: row[0])
        return cls(dict(sequences))

    def summary(self) -> Dict[str, float]:
        tx_counts = [len(seq) for seq in self.sequences.values()]
        item_counts = [len(trans) for seq in self.sequences.values() for _, trans in seq]

        def block(values: List[int], prefix: str) -> Dict[str, float]:
            if not values:
                return {
                    f"{prefix}_min": 0,
                    f"{prefix}_max": 0,
                    f"{prefix}_mean": 0,
                    f"{prefix}_stdev": 0,
                }
            return {
                f"{prefix}_min": min(values),
                f"{prefix}_max": max(values),
                f"{prefix}_mean": statistics.mean(values),
                f"{prefix}_stdev": statistics.pstdev(values),
            }

        result: Dict[str, float] = {
            "num_sequences": len(self.sequences),
            "num_items": len(self.items),
            "num_transactions": sum(tx_counts),
        }
        result.update(block(tx_counts, "transactions_per_sequence"))
        result.update(block(item_counts, "items_per_transaction"))
        return result


def _i_extend(db: SequenceDatabase, parent: Record, item: Item) -> IdList:
    """I-extension: dodanie pozycji do ostatniego elementu (ten sam TId)."""
    output: IdList = {}
    occurrences = db.item_occ[item]
    for sid, ends in parent.idlist.items():
        common = ends & occurrences.get(sid, set())
        if common:
            output[sid] = common
    return output


def _s_extend(db: SequenceDatabase, parent: Record, item: Item) -> IdList:
    """S-extension: dodanie nowego elementu występującego później."""
    output: IdList = {}
    occurrences = db.item_occ[item]
    for sid, ends in parent.idlist.items():
        item_tids = occurrences.get(sid, set())
        if not item_tids:
            continue
        valid = {tid for tid in item_tids if any(end < tid for end in ends)}
        if valid:
            output[sid] = valid
    return output


def _remove_last_occurrence(pattern: Pattern) -> Tuple[Pattern, Tuple[str, Item]]:
    """Zwraca prefiks G(P) oraz typ ostatniego rozszerzenia I/S.

    Pozycje w itemsecie są kanonizowane leksykograficznie. Jeśli ostatni
    itemset ma kilka pozycji, usuwana jest największa z nich (I-extension).
    W przeciwnym razie usuwany jest cały ostatni itemset (S-extension).
    """
    last = pattern[-1]
    if len(last) > 1:
        return pattern[:-1] + (last[:-1],), ("I", last[-1])
    return pattern[:-1], ("S", last[0])


def _append_i(prefix: Pattern, item: Item) -> Pattern:
    if not prefix:
        raise ValueError("I-extension pustego prefiksu jest niedozwolone")
    last = prefix[-1]
    if item in last:
        raise ValueError("Pozycje w jednym elemencie nie mogą się powtarzać")
    return prefix[:-1] + (tuple(sorted(last + (item,))),)


def _append_s(prefix: Pattern, item: Item) -> Pattern:
    return prefix + ((item,),)


def _join_pair(prefix: Pattern, left_desc: Tuple[str, Item], right_desc: Tuple[str, Item]) -> List[Pattern]:
    """Reguły łączenia par wzorców z tabeli SPADE z wykładu.

    Członkowie jednej klasy równoważności mają wspólny prefiks G(P) i
    różnią się jednym końcowym rozszerzeniem. Z pary wzorców długości k
    tworzone są kandydaty długości k+1.
    """
    left_kind, x = left_desc
    right_kind, y = right_desc
    candidates: List[Pattern] = []

    if left_kind == "I" and right_kind == "I":
        if x != y:
            candidates.append(_append_i(_append_i(prefix, x), y))
    elif left_kind == "I" and right_kind == "S":
        candidates.append(_append_s(_append_i(prefix, x), y))
    elif left_kind == "S" and right_kind == "I":
        candidates.append(_append_s(_append_i(prefix, y), x))
    else:  # S/S
        if x == y:
            candidates.append(_append_s(_append_s(prefix, x), x))
        else:
            # <G(P)(xy)>, <G(P)(x)(y)> oraz <G(P)(y)(x)>
            smaller, larger = sorted((x, y))
            candidates.append(_append_i(_append_s(prefix, smaller), larger))
            candidates.append(_append_s(_append_s(prefix, x), y))
            candidates.append(_append_s(_append_s(prefix, y), x))
    return candidates


def _register_candidate(stats: MiningStats, record: Record) -> None:
    length = pattern_length(record.pattern)
    level = stats.by_length[length]
    level.candidates += 1
    level.candidate_support_sum += record.support
    level.candidate_tidlist_sum += record.tidlist_length
    stats.longest_candidate = max(stats.longest_candidate, length)


def _register_pattern(stats: MiningStats, record: Record) -> None:
    length = pattern_length(record.pattern)
    level = stats.by_length[length]
    level.patterns += 1
    level.pattern_support_sum += record.support
    level.pattern_tidlist_sum += record.tidlist_length
    stats.longest_pattern = max(stats.longest_pattern, length)
    stats.discovered.append(record)


def _initial_patterns(db: SequenceDatabase, min_sup: int, stats: MiningStats) -> List[Record]:
    records: List[Record] = []
    for item in db.items:
        record = Record(((item,),), {sid: set(tids) for sid, tids in db.item_occ[item].items()})
        _register_candidate(stats, record)
        if record.support >= min_sup:
            _register_pattern(stats, record)
            records.append(record)
    return records


def _join_equivalence_class(
    db: SequenceDatabase,
    members: List[Record],
    min_sup: int,
    stats: MiningStats,
) -> List[List[Record]]:
    """Łączy pary członków klasy i zwraca częste klasy potomne.

    Każdy unikalny kandydat jest rejestrowany dokładnie raz. Kolejność
    kandydatów wynika z kolejności par wzorców rodzicielskich.
    """
    if not members:
        return []
    prefix, _ = _remove_last_occurrence(members[0].pattern)
    parent_map = {record.pattern: record for record in members}
    descriptors = [_remove_last_occurrence(record.pattern)[1] for record in members]
    seen: Set[Pattern] = set()
    child_classes: Dict[Pattern, List[Record]] = {}

    for i, left_desc in enumerate(descriptors):
        for j in range(i, len(descriptors)):
            right_desc = descriptors[j]
            for candidate_pattern in _join_pair(prefix, left_desc, right_desc):
                if candidate_pattern in seen:
                    continue
                seen.add(candidate_pattern)
                candidate_parent_pattern, (extension_kind, item) = _remove_last_occurrence(candidate_pattern)
                parent = parent_map.get(candidate_parent_pattern)
                if parent is None:
                    # Kandydat nie może być utworzony w tej klasie bez częstego rodzica.
                    continue
                idlist = _i_extend(db, parent, item) if extension_kind == "I" else _s_extend(db, parent, item)
                candidate = Record(candidate_pattern, idlist)
                _register_candidate(stats, candidate)
                if candidate.support >= min_sup:
                    _register_pattern(stats, candidate)
                    child_prefix, _ = _remove_last_occurrence(candidate_pattern)
                    child_classes.setdefault(child_prefix, []).append(candidate)

    return list(child_classes.values())


def d_spade(db: SequenceDatabase, min_sup: int, input_file: str = "") -> MiningStats:
    """Wykładowy SPADE z przeszukiwaniem klas równoważności w głąb."""
    if min_sup < 1:
        raise ValueError("sup musi być >= 1")
    stats = MiningStats("dSPADE", input_file, min_sup, None)
    roots = _initial_patterns(db, min_sup, stats)

    def dfs(members: List[Record]) -> None:
        for child_class in _join_equivalence_class(db, members, min_sup, stats):
            dfs(child_class)

    dfs(roots)
    return stats


def max_length_d_spade(
    db: SequenceDatabase, min_sup: int, max_length: int, input_file: str = ""
) -> MiningStats:
    """Wykładowy SPADE DFS ograniczony długością wzorca."""
    if min_sup < 1:
        raise ValueError("sup musi być >= 1")
    if max_length < 1:
        raise ValueError("maxLength musi być >= 1")
    stats = MiningStats("maxLength-dSPADE", input_file, min_sup, max_length)
    roots = _initial_patterns(db, min_sup, stats)

    def dfs(members: List[Record]) -> None:
        if not members or pattern_length(members[0].pattern) >= max_length:
            return
        for child_class in _join_equivalence_class(db, members, min_sup, stats):
            dfs(child_class)

    dfs(roots)
    return stats


def b_spade(db: SequenceDatabase, min_sup: int, input_file: str = "") -> MiningStats:
    """Wykładowy SPADE z przeszukiwaniem klas równoważności wszerz."""
    if min_sup < 1:
        raise ValueError("sup musi być >= 1")
    stats = MiningStats("bSPADE", input_file, min_sup, None)
    roots = _initial_patterns(db, min_sup, stats)
    queue = deque([roots])
    while queue:
        members = queue.popleft()
        queue.extend(_join_equivalence_class(db, members, min_sup, stats))
    return stats


def max_length_b_spade(
    db: SequenceDatabase, min_sup: int, max_length: int, input_file: str = ""
) -> MiningStats:
    """Wykładowy SPADE BFS ograniczony długością wzorca."""
    if min_sup < 1:
        raise ValueError("sup musi być >= 1")
    if max_length < 1:
        raise ValueError("maxLength musi być >= 1")
    stats = MiningStats("maxLength-bSPADE", input_file, min_sup, max_length)
    roots = _initial_patterns(db, min_sup, stats)
    queue = deque([roots])
    while queue:
        members = queue.popleft()
        if members and pattern_length(members[0].pattern) < max_length:
            queue.extend(_join_equivalence_class(db, members, min_sup, stats))
    return stats


def run_algorithm(
    algorithm: str,
    input_path: str | Path,
    min_sup: int,
    max_length: Optional[int] = None,
) -> MiningStats:
    start = perf_counter()
    read_start = perf_counter()
    db = SequenceDatabase.read(input_path)
    read_end = perf_counter()
    mining_start = perf_counter()

    if algorithm == "dSPADE":
        stats = d_spade(db, min_sup, str(input_path))
    elif algorithm == "bSPADE":
        stats = b_spade(db, min_sup, str(input_path))
    elif algorithm == "maxLength-dSPADE":
        if max_length is None:
            raise ValueError("maxLength jest wymagane dla maxLength-dSPADE")
        stats = max_length_d_spade(db, min_sup, int(max_length), str(input_path))
    elif algorithm == "maxLength-bSPADE":
        if max_length is None:
            raise ValueError("maxLength jest wymagane dla maxLength-bSPADE")
        stats = max_length_b_spade(db, min_sup, int(max_length), str(input_path))
    else:
        raise ValueError(f"Nieznany algorytm: {algorithm}")

    mining_end = perf_counter()
    stats.read_time = read_end - read_start
    stats.mining_time = mining_end - mining_start
    stats.total_without_read = stats.mining_time
    stats.total_time = mining_end - start
    stats.dataset_summary = db.summary()
    return stats


def output_stem(stats: MiningStats) -> str:
    summary = stats.dataset_summary
    fname = Path(stats.input_file).stem
    base = (
        f"{stats.algorithm}_{fname}_d{int(summary['num_sequences'])}"
        f"_t{int(summary['num_transactions'])}_i{int(summary['num_items'])}_s{stats.min_sup}"
    )
    if stats.max_length is not None:
        base += f"_L{stats.max_length}"
    return base


def _totals(stats: MiningStats) -> Tuple[int, int, int, int, int, int]:
    levels = list(stats.by_length.values())
    return (
        sum(level.candidates for level in levels),
        sum(level.candidate_support_sum for level in levels),
        sum(level.candidate_tidlist_sum for level in levels),
        sum(level.patterns for level in levels),
        sum(level.pattern_support_sum for level in levels),
        sum(level.pattern_tidlist_sum for level in levels),
    )


def _stat_text(stats: MiningStats) -> str:
    summary = stats.dataset_summary
    (
        total_candidates,
        candidate_support_sum,
        candidate_tidlist_sum,
        total_patterns,
        pattern_support_sum,
        pattern_tidlist_sum,
    ) = _totals(stats)

    labels = {
        "num_sequences": "liczba sekwencji danych",
        "num_transactions": "liczba transakcji",
        "num_items": "liczba różnych pozycji",
        "transactions_per_sequence_min": "min. liczba transakcji w sekwencji",
        "transactions_per_sequence_max": "maks. liczba transakcji w sekwencji",
        "transactions_per_sequence_mean": "średnia liczba transakcji w sekwencji",
        "transactions_per_sequence_stdev": "odchylenie standardowe liczby transakcji w sekwencji",
        "items_per_transaction_min": "min. liczba pozycji w transakcji",
        "items_per_transaction_max": "maks. liczba pozycji w transakcji",
        "items_per_transaction_mean": "średnia liczba pozycji w transakcji",
        "items_per_transaction_stdev": "odchylenie standardowe liczby pozycji w transakcji",
    }

    lines = [
        f"algorytm: {stats.algorithm}",
        f"plik wejściowy: {stats.input_file}",
    ]
    for key in labels:
        value = summary[key]
        if isinstance(value, float) and not value.is_integer():
            lines.append(f"{labels[key]}: {value:.6f}")
        else:
            lines.append(f"{labels[key]}: {int(value)}")
    lines.append(f"sup: {stats.min_sup}")
    if stats.max_length is not None:
        lines.append(f"maxLength: {stats.max_length}")
    lines.extend(
        [
            f"czas odczytu pliku wejściowego: {stats.read_time:.9f} s",
            f"czas wyznaczania wzorców: {stats.mining_time:.9f} s",
            f"czas zapisywania wyników: {stats.write_time:.9f} s",
            f"całkowity czas bez odczytu: {stats.total_without_read:.9f} s",
            f"całkowity czas wykonania: {stats.total_time:.9f} s",
            f"długość najdłuższej sekwencji kandydującej: {stats.longest_candidate}",
            f"długość najdłuższego odkrytego wzorca sekwencyjnego: {stats.longest_pattern}",
            f"# wszystkich utworzonych kandydatów: {total_candidates}",
            f"suma wsparć wszystkich kandydatów: {candidate_support_sum}",
            f"suma długości tidlist wszystkich kandydatów: {candidate_tidlist_sum}",
            f"# wszystkich odkrytych wzorców sekwencyjnych: {total_patterns}",
            f"suma wsparć wszystkich wzorców: {pattern_support_sum}",
            f"suma długości tidlist wszystkich wzorców: {pattern_tidlist_sum}",
        ]
    )

    # Specyfikacja wymaga poziomów aż do najdłuższego wzorca + 1.
    max_required = max(stats.longest_candidate, stats.longest_pattern + 1)
    if stats.max_length is not None:
        max_required = max(max_required, stats.longest_pattern + 1)
    for length in range(1, max_required + 1):
        level = stats.by_length[length]
        lines.append(
            f"k={length}: kandydaci={level.candidates}, "
            f"suma_wsparć_kandydatów={level.candidate_support_sum}, "
            f"suma_tidlist_kandydatów={level.candidate_tidlist_sum}; "
            f"wzorce={level.patterns}, "
            f"suma_wsparć_wzorców={level.pattern_support_sum}, "
            f"suma_tidlist_wzorców={level.pattern_tidlist_sum}"
        )
    if stats.max_length is not None and stats.longest_pattern >= stats.max_length:
        lines.append(
            f"uwaga: kandydaci o długości większej niż {stats.max_length} nie byli generowani "
            "z powodu ograniczenia maxLength"
        )
    return "\n".join(lines) + "\n"


def write_results(stats: MiningStats, out_dir: str | Path) -> Tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(stats)
    out_path = out_dir / f"OUT_{stem}.csv"
    stat_path = out_dir / f"STAT_{stem}.txt"

    write_start = perf_counter()
    with out_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(
            [
                "długość wzorca",
                "liczba elementów",
                "długość tidlisty",
                "wsparcie sup",
                "wzorzec sekwencyjny",
            ]
        )
        for record in stats.discovered:
            writer.writerow(
                [
                    pattern_length(record.pattern),
                    len(record.pattern),
                    record.tidlist_length,
                    record.support,
                    pattern_to_string(record.pattern),
                ]
            )

    # Pierwszy zapis STAT pozwala uwzględnić koszt fizycznego utworzenia pliku.
    stat_path.write_text(_stat_text(stats), encoding="utf-8")
    stats.write_time = perf_counter() - write_start
    stats.total_without_read = stats.mining_time + stats.write_time
    stats.total_time = stats.read_time + stats.total_without_read
    # Końcowa aktualizacja pól czasowych; jej mikroskopijny koszt nie jest doliczany,
    # aby uniknąć nieskończonej rekalkulacji czasu zapisu samego pliku STAT.
    stat_path.write_text(_stat_text(stats), encoding="utf-8")
    return out_path, stat_path
