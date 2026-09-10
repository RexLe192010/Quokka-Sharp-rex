"""Create compact summary plots from encoding_optimization.csv."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "benchmarks" / "results" / "encoding_optimization.csv"
OUTPUT_PATH = ROOT / "benchmarks" / "results" / "encoding_optimization_summary.png"


def read_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as stream:
        return [row for row in csv.DictReader(stream) if row["status"] == "ok"]


def main() -> None:
    import matplotlib.pyplot as plt

    rows = read_rows()
    groups = defaultdict(list)
    for row in rows:
        source = "synthetic stress" if row["circuit"].startswith("synthetic/") else "repository fixtures"
        groups[(source, row["basis"])].append(row)

    metrics = [
        ("gate_reduction", "Gates"),
        ("variable_reduction", "Variables"),
        ("clause_reduction", "Clauses"),
        ("weighted_variable_reduction", "Weighted variables"),
    ]
    sources = ["repository fixtures", "synthetic stress"]
    bases = ["computational", "pauli"]
    colors = {"computational": "#2a6fbb", "pauli": "#e07a2d"}

    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    for axis, (metric, title) in zip(axes.flat, metrics):
        positions = []
        values = []
        labels = []
        for source_index, source in enumerate(sources):
            for basis_index, basis in enumerate(bases):
                sample = [float(row[metric]) * 100 for row in groups[(source, basis)]]
                positions.append(source_index * 3 + basis_index)
                values.append(sample)
                labels.append(f"{source}\n{basis}")

        axis.boxplot(values, positions=positions, widths=0.55, patch_artist=True,
                     boxprops={"facecolor": "#d9e2f3"}, medianprops={"color": "#222222"})
        for position, sample, label in zip(positions, values, labels):
            axis.scatter([position] * len(sample), sample, s=12, alpha=0.45,
                         color=colors["computational"] if label.endswith("computational") else colors["pauli"])
        axis.axhline(0, color="black", linewidth=0.7)
        axis.set_title(title)
        axis.set_ylabel("Reduction (%)")
        axis.set_xticks(positions)
        axis.set_xticklabels(labels, fontsize=8)
        axis.grid(axis="y", alpha=0.25)

    figure.suptitle("Quokka-Sharp optimization reduction summary")
    figure.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT_PATH, dpi=180)
    plt.close(figure)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
