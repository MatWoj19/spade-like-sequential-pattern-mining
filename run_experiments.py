from pathlib import Path
import csv
import shutil

from spade_like.core import run_algorithm, write_results

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
DATASETS = {
    "small.txt": [2, 3],
    "BMSWebView1.txt": [1000, 2000],
    "sign.txt": [400, 600],
    "kosarak10k.txt": [1000, 2000],
}


def main() -> None:
    # Pełna odtwarzalność: stare OUT/STAT i podsumowanie nie są mieszane z nowymi.
    if RESULTS.exists():
        shutil.rmtree(RESULTS)
    RESULTS.mkdir(parents=True)

    rows = []
    for dataset, supports in DATASETS.items():
        path = ROOT / "data" / dataset
        for support in supports:
            for algorithm in ["dSPADE", "bSPADE"]:
                stats = run_algorithm(algorithm, path, support)
                write_results(stats, RESULTS)
                rows.append(_row(dataset, stats, "∞"))
            for max_length in [2, 3, 4]:
                for algorithm in ["maxLength-dSPADE", "maxLength-bSPADE"]:
                    stats = run_algorithm(algorithm, path, support, max_length)
                    write_results(stats, RESULTS)
                    rows.append(_row(dataset, stats, max_length))

    with (RESULTS / "experiment_summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Zapisano {len(rows)} eksperymentów w {RESULTS}")


def _row(dataset: str, stats, max_length):
    return {
        "dataset": dataset,
        "algorithm": stats.algorithm,
        "sup": stats.min_sup,
        "maxLength": max_length,
        "patterns": len(stats.discovered),
        "candidates": sum(level.candidates for level in stats.by_length.values()),
        "longest": stats.longest_pattern,
        "mining_s": f"{stats.mining_time:.9f}",
        "write_s": f"{stats.write_time:.9f}",
        "total_s": f"{stats.total_time:.9f}",
    }


if __name__ == "__main__":
    main()
