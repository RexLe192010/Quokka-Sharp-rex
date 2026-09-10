"""Benchmark reusable gate templates with and without subexpression caching."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "quokka_sharp"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from quokka_sharp.encoding.template_encoder import TemplateEncoder


OUTPUT = ROOT / "benchmarks" / "results" / "template_encoding.csv"
PLOT_OUTPUT = ROOT / "benchmarks" / "results" / "template_encoding.png"


def clause_width(encoder: TemplateEncoder) -> float:
    if not encoder.clauses:
        return 0.0
    return sum(len(clause) for clause in encoder.clauses) / len(encoder.clauses)


def run_case(name: str, repeats: int, operation: str, cache_enabled: bool) -> dict[str, object]:
    encoder = TemplateEncoder(initial_variables=3, cache_enabled=cache_enabled)
    for _ in range(repeats):
        if operation == "cnot":
            encoder.cnot_transition(1, 2)
        elif operation == "toffoli":
            encoder.toffoli_transition(1, 2, 3)
        else:
            raise ValueError(operation)
    stats = encoder.stats()
    return {
        "case": name,
        "operation": operation,
        "repeats": repeats,
        "cache": "on" if cache_enabled else "off",
        "variables": stats.variables,
        "clauses": stats.clauses,
        "avg_clause_width": clause_width(encoder),
        "cache_hits": stats.cache_hits,
        "cache_entries": stats.cache_entries,
    }


def main() -> None:
    rows = []
    for operation in ("cnot", "toffoli"):
        for repeats in (1, 2, 4, 8, 16, 32, 64):
            case = f"{operation}-{repeats}"
            rows.append(run_case(case, repeats, operation, False))
            rows.append(run_case(case, repeats, operation, True))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for axis, operation, metric, title in (
        (axes[0], "cnot", "variables", "Variables"),
        (axes[1], "toffoli", "clauses", "Clauses"),
    ):
        for cache, color in (("off", "#bdbdbd"), ("on", "#2a6fbb")):
            sample = [row for row in rows if row["operation"] == operation and row["cache"] == cache]
            sample.sort(key=lambda row: int(row["repeats"]))
            axis.plot(
                [int(row["repeats"]) for row in sample],
                [int(row[metric]) for row in sample],
                marker="o",
                color=color,
                label=f"cache {cache}",
            )
        axis.set_xscale("log", base=2)
        axis.set_title(f"{operation.upper()} template: {title}")
        axis.set_xlabel("Repeated identical relation")
        axis.set_ylabel(title)
        axis.grid(alpha=0.25)
        axis.legend()
    figure.suptitle("Gate-specific template common-subexpression reuse")
    figure.tight_layout()
    figure.savefig(PLOT_OUTPUT, dpi=180)
    plt.close(figure)
    print(f"rows={len(rows)}")
    print(f"csv={OUTPUT}")
    print(f"plot={PLOT_OUTPUT}")


if __name__ == "__main__":
    main()
