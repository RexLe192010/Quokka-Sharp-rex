"""Benchmark baseline versus the opt-in circuit optimizer.

This benchmark measures CNF construction only. It deliberately does not call
an external WMC solver, so results are reproducible without GPMC or Ganak.
"""

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
from quokka_sharp.encoding.optimized import optimize_circuit
from quokka_sharp.encoding.qasm_parser import Circuit, QASMparser


FIXTURE_DIRS = ("single_qubit", "multi_qubit", "equiv_pairs", "verify", "synthesis")


def _synthetic_circuits() -> list[tuple[str, Circuit]]:
    circuits = []

    circuit = Circuit()
    circuit.n = 1
    for _ in range(20):
        circuit.add_single("h", 0)
        circuit.add_single("h", 0)
        circuit.add_single("t", 0)
        circuit.add_single("tdg", 0)
    circuits.append(("synthetic/cancellation-heavy-1q", circuit))

    circuit = Circuit()
    circuit.n = 2
    for _ in range(20):
        circuit.add_double("cx", 0, 1)
        circuit.add_double("cx", 0, 1)
        circuit.add_double("cz", 0, 1)
        circuit.add_double("cz", 0, 1)
    circuits.append(("synthetic/cancellation-heavy-2q", circuit))

    circuit = Circuit()
    circuit.n = 2
    for _ in range(10):
        circuit.add_single("h", 0)
        circuit.add_double("cx", 0, 1)
        circuit.add_single("tdg", 1)
        circuit.add_single("t", 1)
        circuit.add_double("cx", 0, 1)
        circuit.add_single("h", 0)
    circuits.append(("synthetic/mixed-cancellation", circuit))

    return circuits


def _fixture_circuits(
    fixture_root: Path,
) -> tuple[list[tuple[str, Circuit]], list[dict[str, object]]]:
    circuits = []
    errors = []
    for directory in FIXTURE_DIRS:
        for qasm_path in sorted((fixture_root / directory).glob("*.qasm")):
            name = str(qasm_path.relative_to(fixture_root))
            try:
                circuits.append((name, QASMparser(str(qasm_path))))
            except Exception as error:
                errors.append({
                    "circuit": name,
                    "basis": "all",
                    "status": "error",
                    "error": f"parser: {type(error).__name__}: {error}",
                })
    return circuits, errors


def _cnf_metrics(circuit: Circuit, computational_basis: bool) -> dict[str, float | int]:
    start = time.perf_counter()
    cnf = QASM2CNF(circuit, computational_basis=computational_basis)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return {
        "gates": len(circuit.circ),
        "variables": cnf.vars.var,
        "clauses": cnf.clause,
        "weighted_variables": sum(weight is not None for weight in cnf.weights),
        "cnf_build_ms": elapsed_ms,
    }


def _ratio(original: float | int, optimized: float | int) -> float:
    if original == 0:
        return 0.0
    return 1.0 - (optimized / original)


def collect_rows(fixture_root: Path) -> list[dict[str, object]]:
    circuits, rows = _fixture_circuits(fixture_root)
    circuits += _synthetic_circuits()
    for name, circuit in circuits:
        optimized = optimize_circuit(circuit)
        for basis_name, computational_basis in (("computational", True), ("pauli", False)):
            try:
                baseline = _cnf_metrics(circuit, computational_basis)
                reduced = _cnf_metrics(optimized, computational_basis)
            except Exception as error:
                rows.append({
                    "circuit": name,
                    "basis": basis_name,
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                })
                continue

            row = {
                "circuit": name,
                "basis": basis_name,
                "status": "ok",
                "error": "",
                "original_gates": baseline["gates"],
                "optimized_gates": reduced["gates"],
                "gate_reduction": _ratio(baseline["gates"], reduced["gates"]),
                "original_variables": baseline["variables"],
                "optimized_variables": reduced["variables"],
                "variable_reduction": _ratio(baseline["variables"], reduced["variables"]),
                "original_clauses": baseline["clauses"],
                "optimized_clauses": reduced["clauses"],
                "clause_reduction": _ratio(baseline["clauses"], reduced["clauses"]),
                "original_weighted_variables": baseline["weighted_variables"],
                "optimized_weighted_variables": reduced["weighted_variables"],
                "weighted_variable_reduction": _ratio(
                    baseline["weighted_variables"], reduced["weighted_variables"]
                ),
                "original_cnf_build_ms": baseline["cnf_build_ms"],
                "optimized_cnf_build_ms": reduced["cnf_build_ms"],
            }
            rows.append(row)
    return rows


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row})
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_plot(rows: list[dict[str, object]], output_path: Path) -> None:
    import matplotlib.pyplot as plt

    ok_rows = [row for row in rows if row.get("status") == "ok"]
    names = [str(row["circuit"]) for row in ok_rows]
    if not names:
        return

    figure, axes = plt.subplots(3, 1, figsize=(15, max(9, len(names) * 0.22)), sharex=True)
    positions = list(range(len(names)))
    width = 0.38

    for axis, original_key, optimized_key, title in (
        (axes[0], "original_gates", "optimized_gates", "Gate count"),
        (axes[1], "original_variables", "optimized_variables", "CNF variables"),
        (axes[2], "original_clauses", "optimized_clauses", "CNF clauses"),
    ):
        original = [int(row[original_key]) for row in ok_rows]
        optimized = [int(row[optimized_key]) for row in ok_rows]
        axis.bar([position - width / 2 for position in positions], original, width, label="baseline")
        axis.bar([position + width / 2 for position in positions], optimized, width, label="optimized")
        axis.set_ylabel(title)
        axis.grid(axis="y", alpha=0.25)
        axis.legend()

    axes[-1].set_xticks(positions)
    axes[-1].set_xticklabels(names, rotation=75, ha="right", fontsize=7)
    figure.suptitle("Quokka-Sharp encoding optimization: baseline vs optimized")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=REPO_ROOT / "tests" / "qasm_fixtures",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "results" / "encoding_optimization.csv",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "results" / "encoding_optimization.png",
    )
    args = parser.parse_args()

    rows = collect_rows(args.fixture_root)
    write_csv(rows, args.csv)
    write_plot(rows, args.plot)
    successful = sum(row.get("status") == "ok" for row in rows)
    failed = len(rows) - successful
    print(f"rows={len(rows)} successful={successful} failed={failed}")
    print(f"csv={args.csv}")
    print(f"plot={args.plot}")


if __name__ == "__main__":
    main()
