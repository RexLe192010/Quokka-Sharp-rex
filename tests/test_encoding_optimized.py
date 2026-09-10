from copy import deepcopy
import unittest

from quokka_sharp.encoding.cnf import QASM2CNF
from quokka_sharp.encoding.optimized import optimize_circuit, optimized_qasm2cnf
from quokka_sharp.encoding.qasm_parser import Circuit


def single(gate, qubit=0):
    circuit = Circuit()
    circuit.n = 1
    circuit.add_single(gate, qubit)
    return circuit


class OptimizedEncodingTests(unittest.TestCase):
    def test_adjacent_inverse_pairs_are_removed_without_mutating_input(self):
        circuit = Circuit()
        circuit.n = 1
        circuit.add_single("h", 0)
        circuit.add_single("h", 0)
        circuit.add_single("t", 0)
        circuit.add_single("tdg", 0)
        circuit.add_single("id", 0)
        original = deepcopy(circuit)

        optimized = optimize_circuit(circuit)

        self.assertEqual(optimized.circ, [])
        self.assertEqual(circuit.circ, original.circ)
        self.assertEqual(circuit.tgate, original.tgate)
        self.assertEqual(optimized.n, circuit.n)

    def test_two_qubit_inverse_requires_same_operands_and_order(self):
        circuit = Circuit()
        circuit.n = 2
        circuit.add_double("cx", 0, 1)
        circuit.add_double("cx", 1, 0)
        circuit.add_double("cx", 1, 0)

        optimized = optimize_circuit(circuit)

        self.assertEqual(optimized.circ, [["cx", 0, 1]])

    def test_optimizer_does_not_cross_measurements_or_conditionals(self):
        circuit = Circuit()
        circuit.n = 1
        circuit.cregs["c"] = 1
        circuit.circ = [
            ["h", 0],
            ["measure", 0, "c", 0],
            ["h", 0],
            ["if", ("c", 0), 1, "x", 0],
            ["x", 0],
        ]

        optimized = optimize_circuit(circuit)

        self.assertEqual(optimized.circ, circuit.circ)

    def test_optimized_cnf_is_smaller_for_canceling_circuit(self):
        circuit = Circuit()
        circuit.n = 1
        circuit.add_single("h", 0)
        circuit.add_single("h", 0)

        baseline = QASM2CNF(circuit, computational_basis=True)
        optimized = optimized_qasm2cnf(circuit, computational_basis=True)

        self.assertLess(optimized.vars.var, baseline.vars.var)
        self.assertLess(optimized.clause, baseline.clause)
        self.assertEqual(optimized.circuit.circ, [])
        self.assertEqual(circuit.circ, [["h", 0], ["h", 0]])

    def test_identity_and_metadata_are_preserved(self):
        circuit = single("id")
        circuit.ancillas = 2
        circuit.measurements[("c", 0)] = 0
        circuit.cregs["c"] = 1

        optimized = optimize_circuit(circuit)

        self.assertEqual(optimized.circ, [])
        self.assertEqual(optimized.n, 1)
        self.assertEqual(optimized.ancillas, 2)
        self.assertEqual(optimized.measurements, circuit.measurements)
        self.assertEqual(optimized.cregs, circuit.cregs)
        self.assertEqual(optimized.tgate, 0)
        self.assertFalse(optimized.has_rotations)
