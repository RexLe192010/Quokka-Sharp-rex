"""Benchmark direct CNF clause optimization after quantum encoding."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "quokka_sharp"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from quokka_sharp.encoding.cnf import QASM2CNF
from quokka_sharp.encoding.optimized_cnf import optimize_cnf
from quokka_sharp.encoding.qasm_parser import Circuit, QASMparser

FIXTURE_DIRS = ("single_qubit", "multi_qubit", "equiv_pairs", "verify", "synthesis")


def synthetic_circuits() -> list[tuple[str, Circuit]]:
    circuits = []

    circuit = Circuit()
    circuit.n = 1
    for _ in range(20):
        circuit.add_single("h", 0)
        circuit.add_single("h", 0)
    circuits.append(("synthetic/repeated-h", circuit))

    circuit = Circuit()
    circuit.n = 2
    for _ in range(12):
        circuit.add_double("cx", 0, 1)
        circuit.add_double("cx", 0, 1)
        circuit.add_double("cz", 0, 1)
        circuit.add_double("cz", 0, 1)
    circuits.append(("synthetic/repeated-two-qubit", circuit))

    return circuits


def load_circuits(root: Path) -> tuple[list[tuple[str, Circuit]], list[dict[str, str]]]:
    circuits = []
    errors = []
    for directory in FIXTURE_DIRS:
        for path in sorted((root / directory).glob("*.qasm")):
            name = str(path.relative_to(root))
            try:
                circuits.append((name, QASMparser(str(path))))
            except Exception as error:
                errors.append({
                    "circuit": name,
                    "basis": "all",
                    "status": "error",
                    "error": f"parser: {type(error).__name__}: {error}",
                })
    return circuits + synthetic_circuits(), errors


def clause_literals(cnf) -> list[tuple[int, ...]]:
    return [
        tuple(int(token) for token in line.split() if token != "0")
        for line in cnf.cons_list
    ]


def metrics(cnf) -> dict[str, float | int]:
    clauses = clause_literals(cnf)
    literal_count = sum(len(clause) for clause in clauses)
    return {
        "variables": cnf.vars.var,
        "clauses": len(clauses),
        "literals": literal_count,
        "avg_clause_width": literal_count / len(clauses) if clauses else 0.0,
        "weighted_variables": sum(weight is not None for weight in cnf.weights),
    }


def reduction(before: float | int, after: float | int) -> float:
    return 0.0 if before == 0 else 1.0 - after / before


def collect_rows(root: Path) -> list[dict[str, object]]:
    circuits, rows = load_circuits(root)
    for name, circuit in circuits:
        for basis, computational_basis in (("computational", True), ("pauli", False)):
            start = time.perf_counter()
            baseline = QASM2CNF(circuit, computational_basis=computational_basis)
            baseline_ms = (time.perf_counter() - start) * 1000.0
            start = time.perf_counter()
            optimized, stats = optimize_cnf(baseline)
            optimize_ms = (time.perf_counter() - start) * 1000.0
            before = metrics(baseline)
            after = metrics(optimized)
            rows.append({
                "circuit": name,
                "basis": basis,
                "status": "ok",
                "error": "",
                "variables": before["variables"],
                "optimized_variables": after["variables"],
                "clauses": before["clauses"],
                "optimized_clauses": after["clauses"],
                "clause_reduction": reduction(before["clauses"], after["clauses"]),
                "literals": before["literals"],
                "optimized_literals": after["literals"],
                "literal_reduction": reduction(before["literals"], after["literals"]),
                "avg_clause_width": before["avg_clause_width"],
                "optimized_avg_clause_width": after["avg_clause_width"],
                "weighted_variables": before["weighted_variables"],
                "optimized_weighted_variables": after["weighted_variables"],
                "duplicate_removed": stats.duplicate_clauses_removed,
                "tautology_removed": stats.tautological_clauses_removed,
                "subsumed_removed": stats.subsumed_clauses_removed,
                "cnf_build_ms": baseline_ms,
                "cnf_optimize_ms": optimize_ms,
            })
    return rows


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_plot(rows: list[dict[str, object]], path: Path) -> None:
    import matplotlib.pyplot as plt

    successful = [row for row in rows if row.get("status") == "ok"]
    if not successful:
        return
    grouped = {basis: [row for row in successful if row["basis"] == basis] for basis in ("computational", "pauli")}
    figure, axes = plt.subplots(2, 2, figsize=(13, 9))
    plots = [
        ("clauses", "optimized_clauses", "CNF clauses"),
        ("literals", "optimized_literals", "Clause literals"),
        ("avg_clause_width", "optimized_avg_clause_width", "Average clause width"),
        ("weighted_variables", "optimized_weighted_variables", "Weighted variables"),
    ]
    for axis, (before_key, after_key, title) in zip(axes.flat, plots):
        for basis, color in (("computational", "#2a6fbb"), ("pauli", "#e07a2d")):
            sample = grouped[basis]
            x = list(range(len(sample)))
            axis.plot(x, [float(row[before_key]) for row in sample], color=color, alpha=0.35)
            axis.plot(x, [float(row[after_key]) for row in sample], color=color, label=f"{basis} optimized")
        axis.set_title(title)
        axis.set_ylabel("count / width")
        axis.grid(axis="y", alpha=0.25)
        axis.legend(fontsize=8)
    figure.suptitle("Direct CNF encoding optimization")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, default=REPO_ROOT / "tests" / "qasm_fixtures")
    parser.add_argument("--csv", type=Path, default=REPO_ROOT / "benchmarks" / "results" / "cnf_encoding_optimization.csv")
    parser.add_argument("--plot", type=Path, default=REPO_ROOT / "benchmarks" / "results" / "cnf_encoding_optimization.png")
    args = parser.parse_args()
    rows = collect_rows(args.fixture_root)
    write_csv(rows, args.csv)
    write_plot(rows, args.plot)
    successful = sum(row.get("status") == "ok" for row in rows)
    print(f"rows={len(rows)} successful={successful} failed={len(rows) - successful}")
    print(f"csv={args.csv}")
    print(f"plot={args.plot}")


if __name__ == "__main__":
    main()
