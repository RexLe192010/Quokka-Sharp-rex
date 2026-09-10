import itertools
import unittest

from quokka_sharp.encoding.template_encoder import TemplateEncoder


def clause_satisfied(clause, assignment):
    return any(assignment[abs(literal)] == (literal > 0) for literal in clause)


def has_extension(encoder, fixed):
    for values in itertools.product((False, True), repeat=encoder.next_variable - len(fixed)):
        assignment = dict(fixed)
        remaining = [variable for variable in range(1, encoder.next_variable + 1) if variable not in assignment]
        assignment.update(zip(remaining, values))
        if all(clause_satisfied(clause, assignment) for clause in encoder.clauses):
            return True
    return False


class TemplateEncoderTests(unittest.TestCase):
    def test_xor_template_matches_truth_table(self):
        encoder = TemplateEncoder(initial_variables=3)
        output = encoder.xor(1, 2)

        for left, right in itertools.product((False, True), repeat=2):
            expected = left ^ right
            self.assertEqual(
                has_extension(encoder, {1: left, 2: right, output: expected}),
                True,
            )
            self.assertEqual(
                has_extension(encoder, {1: left, 2: right, output: not expected}),
                False,
            )

    def test_toffoli_template_matches_truth_table(self):
        encoder = TemplateEncoder(initial_variables=3)
        output = encoder.toffoli_transition(1, 2, 3)

        for control_a, control_b, target in itertools.product((False, True), repeat=3):
            expected = target ^ (control_a and control_b)
            self.assertTrue(
                has_extension(
                    encoder,
                    {1: control_a, 2: control_b, 3: target, output: expected},
                )
            )
            self.assertFalse(
                has_extension(
                    encoder,
                    {1: control_a, 2: control_b, 3: target, output: not expected},
                )
            )

    def test_cache_reuses_identical_subexpressions(self):
        cached = TemplateEncoder(initial_variables=3, cache_enabled=True)
        cached.toffoli_transition(1, 2, 3)
        cached.toffoli_transition(1, 2, 3)

        uncached = TemplateEncoder(initial_variables=3, cache_enabled=False)
        uncached.toffoli_transition(1, 2, 3)
        uncached.toffoli_transition(1, 2, 3)

        self.assertLess(cached.stats().variables, uncached.stats().variables)
        self.assertLess(cached.stats().clauses, uncached.stats().clauses)
        self.assertGreater(cached.stats().cache_hits, 0)


if __name__ == "__main__":
    unittest.main()
