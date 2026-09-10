import itertools
import unittest

from quokka_sharp.encoding.cnf import CNF, QASM2CNF
from quokka_sharp.encoding.optimized_cnf import optimize_cnf, optimized_qasm2cnf
from quokka_sharp.encoding.qasm_parser import Circuit


def parse_clauses(cnf):
    return [
        {int(token) for token in line.split() if token != "0"}
        for line in cnf.cons_list
    ]


def models(cnf):
    clauses = parse_clauses(cnf)
    return {
        assignment
        for assignment in itertools.product((False, True), repeat=cnf.vars.var)
        if all(
            any(assignment[abs(literal) - 1] == (literal > 0) for literal in clause)
            for clause in clauses
        )
    }


class OptimizedCNFTests(unittest.TestCase):
    def test_duplicate_tautology_and_subsumption_are_removed(self):
        cnf = CNF(n=3, computational_basis=True)
        cnf.add_clause([1, 2])
        cnf.add_clause([1, 2])
        cnf.add_clause([1, -1])
        cnf.add_clause([1])
        cnf.add_clause([2, 3])
        before = models(cnf)

        optimized, stats = optimize_cnf(cnf)

        self.assertEqual(models(optimized), before)
        self.assertEqual(parse_clauses(optimized), [{1}, {2, 3}])
        self.assertEqual(stats.duplicate_clauses_removed, 1)
        self.assertEqual(stats.tautological_clauses_removed, 1)
        self.assertEqual(stats.subsumed_clauses_removed, 1)
        self.assertEqual(stats.optimized_clauses, 2)

    def test_weights_and_variables_are_unchanged(self):
        circuit = Circuit()
        circuit.n = 1
        circuit.add_single("h", 0)
        baseline = QASM2CNF(circuit, computational_basis=True)

        optimized, _ = optimize_cnf(baseline)

        self.assertEqual(optimized.vars.var, baseline.vars.var)
        self.assertEqual(optimized.weights, baseline.weights)
        self.assertEqual(optimized.circuit.circ, baseline.circuit.circ)

    def test_generated_encoding_remains_model_equivalent(self):
        circuit = Circuit()
        circuit.n = 1
        circuit.add_single("h", 0)
        circuit.add_single("h", 0)
        baseline = QASM2CNF(circuit, computational_basis=True)

        optimized, stats = optimized_qasm2cnf(circuit, computational_basis=True)

        self.assertEqual(models(optimized), models(baseline))
        self.assertGreaterEqual(stats.clause_reduction, 0.0)
        self.assertGreaterEqual(stats.literal_reduction, 0.0)


if __name__ == "__main__":
    unittest.main()
