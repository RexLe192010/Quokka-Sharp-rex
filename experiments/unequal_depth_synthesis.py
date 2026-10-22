"""Compare iterative synthesis with joint and independent per-wire stopping."""
import argparse
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

from product_synthesis import write_qasm
from run import HERE, configure_environment, load_quokka, prepare_output_directory, resolve_timeout
from synthesis_example import circuit_matrix, synthesize_circuit, unitary_fidelity

CASES = {
    'unequal_2_4': ('ht', 'htht'),
    'unequal_2_6': ('ht', 'hththt'),
    'unequal_2_9': ('ht', 'hthththth'),
}


def factor(sequence):
    return SimpleNamespace(n=1, circ=[[gate, 0] for gate in sequence])


def launch(target, folder, fidelity, budget):
    folder.mkdir(parents=True)
    command = [sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
               str(target), '--output', str(folder), '--fidelity', str(fidelity),
               '--timeout', str(max(1, math.floor(budget)))]
    log = (folder / 'run.log').open('w')
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    log.close()
    return process


def collect(process, folder):
    code = process.wait()
    path = folder / 'result.json'
    if code or not path.exists():
        return dict(status='WORKER_ERROR', returncode=code, validated_success=False)
    report = json.loads(path.read_text())
    log = (folder / 'run.log').read_text()
    report['completed_iterations'] = [
        dict(depth=int(depth), fidelity=float(score), elapsed_s=float(elapsed))
        for depth, score, elapsed in re.findall(
            r'Iteration: (\d+)\s+fidelity:([\d.eE+\-]+)\s+Run Time: ([\d.eE+\-]+)', log)]
    report['solver_calls'] = len(list(folder.glob('*_d4.out')))
    return report


def run_method(qk, target, factors, folder, method, fidelity, budget):
    folder.mkdir(parents=True)
    started = time.perf_counter()
    if method == 'joint':
        child = folder / 'search'
        report = collect(launch(target, child, fidelity, budget), child)
        report['template_slots'] = 2 * report.get('search_depth', 0)
    else:
        threshold = fidelity ** 0.5
        reports = []
        jobs = []
        for wire, component in enumerate(factors):
            path = folder / f'q{wire}.qasm'
            write_qasm(path, [component])
            child = folder / f'q{wire}'
            remaining = budget - (time.perf_counter() - started)
            if remaining < 1:
                reports.append(dict(status='SKIPPED_BUDGET', validated_success=False))
                continue
            process = launch(path, child, threshold, remaining)
            if method == 'sequential':
                reports.append(collect(process, child))
            else:
                jobs.append((process, child))
        reports.extend(collect(process, child) for process, child in jobs)
        report = dict(local_results=reports, local_threshold=threshold,
                      validated_success=False, status='INCOMPLETE',
                      template_slots=sum(r.get('search_depth', 0) for r in reports))
        if len(reports) == 2 and all(r.get('validated_success') for r in reports):
            candidates = [qk.QASMparser(str(folder / f'q{i}' / 'synthesized.qasm'))
                          for i in range(2)]
            combined = folder / 'synthesized.qasm'
            write_qasm(combined, candidates)
            measured = unitary_fidelity(circuit_matrix(qk.QASMparser(str(target))),
                                       circuit_matrix(qk.QASMparser(str(combined))))
            product = math.prod(r['matrix_fidelity'] for r in reports)
            valid = measured + 1e-12 >= fidelity and abs(measured - product) < 1e-9
            report.update(matrix_fidelity=measured, product_fidelity=product,
                          validated_success=valid, status='FOUND' if valid else 'INVALID')
    report.update(method=method, elapsed_s=time.perf_counter() - started,
                  budget_s=budget)
    (folder / 'result.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    parser.add_argument('--timeout', type=int, default=None,
                        help='Budget per method per case (default: config TIMEOUT)')
    parser.add_argument('--fidelity', type=float, default=0.9999)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (args.timeout is not None and args.timeout < 1) or not 0 < args.fidelity < 1:
        parser.error('Positive timeout and 0 < fidelity < 1 required')
    root = args.output if args.worker else HERE / 'outputs' / 'unequal_depth'
    root.mkdir(parents=True, exist_ok=True)
    configure_environment(None, root)
    args.timeout = resolve_timeout(args.timeout)
    if int(args.timeout) != args.timeout or args.timeout < 1:
        parser.error('TIMEOUT must be a positive whole number of seconds')
    args.timeout = int(args.timeout)
    qk = load_quokka('syn')
    if args.worker:
        synthesize_circuit(qk, args.worker, root, args.fidelity, args.timeout)
        return
    for name in args.cases:
        sequences = CASES[name]
        factors = [factor(s) for s in sequences]
        target = HERE / 'circuits' / f'{name}.qasm'
        write_qasm(target, factors)
        output = root / name
        prepare_output_directory(output)
        (output / 'target.qasm').write_text(target.read_text())
        results = dict(target=name, sequences=sequences, input_gates=list(map(len, sequences)),
                       fidelity=args.fidelity, timeout_per_method_s=args.timeout, runs=[])
        for method in ('joint', 'sequential', 'parallel'):
            folder = output / method
            report = run_method(qk, target, factors, folder, method,
                                args.fidelity, args.timeout)
            results['runs'].append(report)
            (output / 'results.json').write_text(json.dumps(results, indent=2))
            depths = ([report.get('search_depth')] if method == 'joint' else
                      [r.get('search_depth') for r in report['local_results']])
            print(f'{name} {method}: {report["status"]}, '
                  f'{report["elapsed_s"]:.3f}s, depths={depths}', flush=True)



if __name__ == '__main__':
    main()
