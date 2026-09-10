"""Reusable Boolean templates for experimenting with gate-specific encodings.

This prototype is intentionally independent of the generated Quokka-Sharp
encoders. It demonstrates common-subexpression reuse for XOR/AND transition
relations, which is a candidate technique for future gate-specific templates.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateStats:
    variables: int
    clauses: int
    cache_hits: int
    cache_entries: int


class TemplateEncoder:
    """Small CNF builder with cached XOR and AND Boolean templates."""

    def __init__(self, initial_variables: int = 0, cache_enabled: bool = True):
        self.next_variable = initial_variables
        self.clauses: list[tuple[int, ...]] = []
        self.cache_enabled = cache_enabled
        self._xor_cache: dict[tuple[int, int], int] = {}
        self._and_cache: dict[tuple[int, int], int] = {}
        self.cache_hits = 0

    def new_variable(self) -> int:
        self.next_variable += 1
        return self.next_variable

    def add_clause(self, *literals: int) -> None:
        self.clauses.append(tuple(literals))

    def equiv_xor(self, output: int, left: int, right: int) -> None:
        self.add_clause(output, left, -right)
        self.add_clause(output, -left, right)
        self.add_clause(-output, left, right)
        self.add_clause(-output, -left, -right)

    def equiv_and(self, output: int, left: int, right: int) -> None:
        self.add_clause(-output, left)
        self.add_clause(-output, right)
        self.add_clause(output, -left, -right)

    @staticmethod
    def _pair(left: int, right: int) -> tuple[int, int]:
        return tuple(sorted((left, right)))

    def xor(self, left: int, right: int) -> int:
        key = self._pair(left, right)
        if self.cache_enabled and key in self._xor_cache:
            self.cache_hits += 1
            return self._xor_cache[key]
        output = self.new_variable()
        self.equiv_xor(output, left, right)
        if self.cache_enabled:
            self._xor_cache[key] = output
        return output

    def and_(self, left: int, right: int) -> int:
        key = self._pair(left, right)
        if self.cache_enabled and key in self._and_cache:
            self.cache_hits += 1
            return self._and_cache[key]
        output = self.new_variable()
        self.equiv_and(output, left, right)
        if self.cache_enabled:
            self._and_cache[key] = output
        return output

    def cnot_transition(self, control: int, target: int) -> int:
        return self.xor(control, target)

    def toffoli_transition(self, control_a: int, control_b: int, target: int) -> int:
        control_product = self.and_(control_a, control_b)
        return self.xor(control_product, target)

    def stats(self) -> TemplateStats:
        return TemplateStats(
            variables=self.next_variable,
            clauses=len(self.clauses),
            cache_hits=self.cache_hits,
            cache_entries=len(self._xor_cache) + len(self._and_cache),
        )
