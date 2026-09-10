"""Opt-in circuit optimizations for Quokka-Sharp encoding.

This module is intentionally separate from the generated encoders and the
existing public package files. It can be used to prepare a Circuit before
passing it to QASM2CNF.
"""

from copy import deepcopy
from typing import Optional

from .cnf import CNF, QASM2CNF
from .qasm_parser import Circuit


_SINGLE_QUBIT_INVERSES = {
    ("h", "h"),
    ("x", "x"),
    ("y", "y"),
    ("z", "z"),
    ("s", "sdg"),
    ("sdg", "s"),
    ("t", "tdg"),
    ("tdg", "t"),
}

_MULTI_QUBIT_INVERSES = {
    ("cx", "cx"),
    ("cy", "cy"),
    ("cz", "cz"),
    ("swap", "swap"),
    ("ccx", "ccx"),
    ("iswap", "iswapdg"),
    ("iswapdg", "iswap"),
    ("cs", "csdg"),
    ("csdg", "cs"),
    ("ct", "ctdg"),
    ("ctdg", "ct"),
    ("csqrtx", "csqrtxdg"),
    ("csqrtxdg", "csqrtx"),
}

_BARRIER_GATES = {"measure", "if"}


def _same_operands(left: list, right: list) -> bool:
    return left[1:] == right[1:]


def _are_inverse(left: list, right: list) -> bool:
    if not left or not right or left[0] in _BARRIER_GATES or right[0] in _BARRIER_GATES:
        return False
    if not _same_operands(left, right):
        return False

    pair = (left[0], right[0])
    if len(left) == 2 and len(right) == 2:
        return pair in _SINGLE_QUBIT_INVERSES
    if len(left) in (3, 4) and len(left) == len(right):
        return pair in _MULTI_QUBIT_INVERSES
    return False


def _recompute_metadata(circuit: Circuit) -> None:
    circuit.tgate = sum(1 for gate in circuit.circ if gate and gate[0] in {"t", "tdg"})
    circuit.has_rotations = any(
        gate and gate[0] in {"rx", "ry", "rz", "rxdg", "rydg", "rzdg"}
        for gate in circuit.circ
    )


def optimize_circuit(circuit: Circuit) -> Circuit:
    """Return a copy with safe adjacent inverse pairs removed.

    Only exact local identities are applied. No gates are reordered, and
    optimization never crosses measurements, conditionals, or unmatched
    gates. The input Circuit is not mutated.
    """
    optimized = deepcopy(circuit)
    stack: list[list] = []

    for gate in optimized.circ:
        if gate and gate[0] == "id":
            continue
        if stack and _are_inverse(stack[-1], gate):
            stack.pop()
        else:
            stack.append(gate)

    optimized.circ = stack
    _recompute_metadata(optimized)
    return optimized


def optimized_qasm2cnf(
    circuit: Circuit,
    computational_basis: bool = False,
    ancillas: int = 0,
    ganak: bool = False,
) -> CNF:
    """Encode an optimized copy of ``circuit`` using the existing CNF path."""
    return QASM2CNF(
        optimize_circuit(circuit),
        computational_basis=computational_basis,
        ancillas=ancillas,
        ganak=ganak,
    )
