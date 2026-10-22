"""Compare joint and per-qubit synthesis of tensor-product targets."""
from contextlib import redirect_stdout
import json
import math
import sys
import time

from synthesis_example import (
    circuit_matrix, local_circuits, synthesize_circuit, unitary_fidelity,
)

PRODUCT_CASES = ('independent_rot2', 'independent_rot3')


def write_qasm(path, factors):
    """Place one-qubit factors on distinct wires, preserving each wire's order."""
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', f'qreg q[{len(factors)}];']
    for qubit, factor in enumerate(factors):
        lines.append(f'// Independent circuit on qubit {qubit}.')
        for gate in factor.circ:
            op = f'{gate[0]}({float(gate[1])!r})' if len(gate) == 3 else gate[0]
            lines.append(f'{op} q[{qubit}];')
    path.write_text('\n'.join(lines) + '\n')


def synthesize_separately(qk, target_path, output, fidelity, timeout):
    """Share one time budget across sequential local searches with equal error budgets."""
    started = time.perf_counter()
    target = qk.QASMparser(str(target_path))
    factors = local_circuits(target)
    local_threshold = fidelity ** (1 / len(factors))
    print(f'Global fidelity threshold: {fidelity}; local threshold: {local_threshold:.12f}')
    print(f'Shared synthesis budget: {timeout}s; qubits are searched sequentially.')
    reports, candidates = [], []
    for qubit, factor in enumerate(factors):
        folder = output / f'q{qubit}'
        folder.mkdir()
        path = folder / 'target.qasm'
        write_qasm(path, [factor])
        # Quokka# uses signal.alarm and requires an integer timeout.
        remaining = math.floor(timeout - (time.perf_counter() - started))
        if remaining < 1:
            reports.append(dict(qubit=qubit, status='SKIPPED_BUDGET', validated_success=False))
            continue
        report = synthesize_circuit(qk, path, folder, local_threshold, remaining,
                                    label=f'{target_path.stem}: q[{qubit}]')
        report['qubit'] = qubit
        reports.append(report)
        candidate_path = folder / 'synthesized.qasm'
        if candidate_path.exists():
            candidates.append(qk.QASMparser(str(candidate_path)))

    report = dict(method='separate', qubits=target.n, requested_fidelity=fidelity,
                  local_threshold=local_threshold, timeout_s=timeout,
                  local_results=reports, validated_success=False,
                  status='INCOMPLETE',
                  synthesis_s=sum(r.get('synthesis_s', 0) for r in reports))
    if len(candidates) == len(factors):
        path = output / 'synthesized.qasm'
        write_qasm(path, candidates)
        composed = qk.QASMparser(str(path))
        local_scores = [unitary_fidelity(circuit_matrix(a), circuit_matrix(b))
                        for a, b in zip(factors, candidates)]
        product = math.prod(local_scores)
        measured = unitary_fidelity(circuit_matrix(target), circuit_matrix(composed))
        agrees = abs(product - measured) < 1e-9
        meets = measured + 1e-12 >= fidelity
        validated = meets and agrees and all(r.get('score_agrees', False) for r in reports)
        report.update(matrix_fidelity=measured, product_fidelity=product,
                      local_fidelities=local_scores, product_agrees=agrees,
                      meets_threshold=meets, validated_success=validated,
                      status='FOUND' if validated else 'INCOMPLETE',
                      candidate_gates=sum(len(c.circ) for c in candidates),
                      candidate_parallel_depth=max(len(c.circ) for c in candidates))
        print(f'Combined fidelity: {measured:.12f}; product of local fidelities: {product:.12f}')
    report['wall_s'] = time.perf_counter() - started
    (output / 'result.json').write_text(json.dumps(report, indent=2))
    return report


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log

    def write(self, text):
        self.terminal.write(text)
        self.log.write(text)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def run_product_synthesis(qk, target_path, output, fidelity, timeout, mode):
    """Each method receives the same total budget and writes a separate log/report."""
    from quokka_sharp import config as qc
    timeout = timeout or qc.CONFIG['TIMEOUT']
    # Validate before invoking either method.
    local_circuits(qk.QASMparser(str(target_path)))
    (output / 'target.qasm').write_text(target_path.read_text())
    methods = ('joint', 'separate') if mode == 'compare' else (mode,)
    results = {}
    for method in methods:
        folder = output / method
        folder.mkdir()
        with (folder / 'run.log').open('w') as log, redirect_stdout(Tee(sys.stdout, log)):
            print(f'\n=== {target_path.stem}: {method} synthesis ===')
            if method == 'joint':
                report = synthesize_circuit(qk, target_path, folder, fidelity, timeout)
            else:
                report = synthesize_separately(qk, target_path, folder, fidelity, timeout)
            results[method] = report
    summary = dict(target=target_path.stem, requested_fidelity=fidelity,
                   timeout_per_method_s=timeout, methods=results)
    (output / 'comparison.json').write_text(json.dumps(summary, indent=2))
    print('\nMethod      Status        Fidelity        Wall (s)')
    for method, report in results.items():
        score = report.get('matrix_fidelity')
        score = f'{score:.12f}' if score is not None else 'unavailable'
        print(f'{method:11s} {report["status"]:13s} {score:15s} {report["wall_s"]:.3f}')
