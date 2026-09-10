"""Semantics-preserving post-processing for generated weighted CNFs.

The optimizer operates after the existing quantum-to-CNF encoder. It leaves
variable identities and literal weights untouched, and only simplifies the
Boolean clause set. This keeps weighted model counts unchanged.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .cnf import CNF, QASM2CNF
from .qasm_parser import Circuit


@dataclass(frozen=True)
class CNFOptimizationStats:
    """Structural statistics before and after clause optimization."""

    original_clauses: int
    optimized_clauses: int
    duplicate_clauses_removed: int
    tautological_clauses_removed: int
    subsumed_clauses_removed: int
    original_total_clause_literals: int
    optimized_total_clause_literals: int

    @property
    def clause_reduction(self) -> float:
        if self.original_clauses == 0:
            return 0.0
        return 1.0 - self.optimized_clauses / self.original_clauses

    @property
    def literal_reduction(self) -> float:
        if self.original_total_clause_literals == 0:
            return 0.0
        return 1.0 - self.optimized_total_clause_literals / self.original_total_clause_literals


def _parse_clause(line: str) -> tuple[int, ...]:
    literals = [int(token) for token in line.split() if token != "0"]
    return tuple(sorted(set(literals)))


def _serialize_clause(clause: tuple[int, ...]) -> str:
    return " ".join(str(literal) for literal in clause) + " 0\n"


def _is_tautology(clause: tuple[int, ...]) -> bool:
    literals = set(clause)
    return any(-literal in literals for literal in literals)


def _subsumption_filter(clauses: list[tuple[int, ...]]) -> list[tuple[int, ...]]:
    """Remove C2 when an existing C1 satisfies C1 subset C2.

    Clauses are processed from shortest to longest. A subsumed clause is
    redundant in CNF and removing it preserves all satisfying assignments.
    """
    kept: list[tuple[int, ...]] = []
    kept_sets: list[frozenset[int]] = []
    for clause in sorted(clauses, key=lambda item: (len(item), item)):
        clause_set = frozenset(clause)
        if any(previous <= clause_set for previous in kept_sets):
            continue
        kept.append(clause)
        kept_sets.append(clause_set)
    return kept


def optimize_cnf(cnf: CNF) -> tuple[CNF, CNFOptimizationStats]:
    """Return a copy with a simplified clause set and optimization statistics.

    The returned CNF has exactly the same variables, weights, circuit metadata,
    and weighted literals as the input. Only ``cons_list`` and ``clause`` are
    changed.
    """
    optimized = deepcopy(cnf)
    original_clauses = [_parse_clause(line) for line in cnf.cons_list]
    original_literal_count = sum(len(clause) for clause in original_clauses)

    unique_clauses = set(original_clauses)
    duplicate_removed = len(original_clauses) - len(unique_clauses)
    non_tautologies = [clause for clause in unique_clauses if not _is_tautology(clause)]
    tautology_removed = len(unique_clauses) - len(non_tautologies)
    filtered = _subsumption_filter(non_tautologies)
    subsumed_removed = len(non_tautologies) - len(filtered)

    filtered.sort(key=lambda item: (len(item), item))
    optimized.cons_list = [_serialize_clause(clause) for clause in filtered]
    optimized.clause = len(filtered)

    stats = CNFOptimizationStats(
        original_clauses=len(original_clauses),
        optimized_clauses=len(filtered),
        duplicate_clauses_removed=duplicate_removed,
        tautological_clauses_removed=tautology_removed,
        subsumed_clauses_removed=subsumed_removed,
        original_total_clause_literals=original_literal_count,
        optimized_total_clause_literals=sum(len(clause) for clause in filtered),
    )
    return optimized, stats


def optimized_qasm2cnf(
    circuit: Circuit,
    computational_basis: bool = False,
    ancillas: int = 0,
    ganak: bool = False,
) -> tuple[CNF, CNFOptimizationStats]:
    """Generate the existing encoding, then simplify its CNF clauses."""
    baseline = QASM2CNF(
        circuit,
        computational_basis=computational_basis,
        ancillas=ancillas,
        ganak=ganak,
    )
    return optimize_cnf(baseline)
