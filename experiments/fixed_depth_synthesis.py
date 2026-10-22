"""Compare joint and separate complete MaxT optimizations at identical depths."""
import argparse
import json
import math
import random
import re
from pathlib import Path
import statistics
import subprocess
import time

from product_synthesis import PRODUCT_CASES, write_qasm
from run import HERE, configure_environment, load_quokka, prepare_output_directory, resolve_timeout
from synthesis_example import circuit_matrix, local_circuits, unitary_fidelity


def product_fidelity(target, candidate):
    """Validate local operations in O(n) small matrices, without a 2**n matrix."""
    if target.n != candidate.n:
        raise ValueError('Target and candidate qubit counts differ')
    scores = [unitary_fidelity(circuit_matrix(a), circuit_matrix(b))
              for a, b in zip(local_circuits(target), local_circuits(candidate))]
    result = math.prod(scores)
    if target.n <= 6:
        dense = unitary_fidelity(circuit_matrix(target), circuit_matrix(candidate))
        assert math.isclose(result, dense, rel_tol=1e-8, abs_tol=1e-14)
    return result, scores


def generated_target(path, qubits, gates, seed):
    """Deterministic mixed rotations; larger sizes preserve earlier wire prefixes."""
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', f'qreg q[{qubits}];',
             f'// Independent wires; {gates} rotations per wire; seed {seed}.']
    for wire in range(qubits):
        rng = random.Random(seed + wire)
        lines.append(f'// q[{wire}]: alternating X/Y/Z axes, angles in radians.')
        for index in range(gates):
            angle = rng.uniform(-math.pi, math.pi)
            lines.append(f'{("rx", "ry", "rz")[index % 3]}({angle!r}) q[{wire}];')
    path.write_text('\n'.join(lines) + '\n')


def solve(qk, target_path, output, depth, deadline):
    """One fixed template, one solver invocation, no acceptance threshold."""
    from quokka_sharp import config as qc
    from quokka_sharp.syn import identity_check, get_result

    output.mkdir(parents=True)
    started = time.perf_counter()
    target = qk.QASMparser(str(target_path))
    original = qk.QASMparser(str(target_path))
    local_circuits(original)
    target.dagger()
    cnf = qk.QASM2CNF(target, computational_basis=False)
    cnf.add_syn_layer({'h', 's', 't'}, depth)
    cnf_path = Path(identity_check(cnf, str(output), 'fixed', depth, onehot_xz=False))
    encoding_s = time.perf_counter() - started
    header = cnf_path.read_text().splitlines()[0].split()
    report = dict(depth=depth, qubits=target.n, variables=int(header[2]),
                  clauses=int(header[3]), encoding_and_setup_s=encoding_s,
                  validated=False)
    # Omitting --threshold makes m_optThreshold false in the local MaxT build.
    command = qc.CONFIG['D4ToolInvocation'].split(' ') + ['-i', str(cnf_path), '--complex', '0']
    report['command'] = command
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return dict(report, status='TIMEOUT', solver_s=0)
    launched = time.perf_counter()
    with (output / 'solver.out').open('w') as stdout, (output / 'solver.err').open('w') as stderr:
        try:
            process = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=remaining)
        except subprocess.TimeoutExpired:
            return dict(report, status='TIMEOUT', solver_s=time.perf_counter() - launched)
    report['solver_s'] = time.perf_counter() - launched
    if process.returncode:
        return dict(report, status='ERROR', returncode=process.returncode)
    log = (output / 'solver.out').read_text()
    assert 'Set the threshold limit' not in log
    for key, label in [('decision_nodes', 'Number of decision'),
                       ('max_component_splits', 'Number of split formula (max)')]:
        match = re.search(re.escape(label) + r': (\d+)', log)
        report[key] = int(match.group(1)) if match else None
    _, score, assignment = get_result(str(output / 'solver.out'), 4**target.n, False)
    if score == 'CRASH':
        return dict(report, status='PARSE_ERROR')
    qasm = cnf.get_syn_qasm(assignment)
    candidate_path = output / 'synthesized.qasm'
    candidate_path.write_text(qasm)
    measured, scores = product_fidelity(original, qk.QASMparser(str(candidate_path)))
    report.update(status='COMPLETE', solver_score=float(score), matrix_fidelity=measured,
                  local_fidelities=scores, validation='product_of_local_2x2_overlaps',
                  validated=math.isclose(measured, float(score), rel_tol=1e-8, abs_tol=1e-14))
    return report


def run_method(qk, target_path, output, depth, timeout, method):
    started = time.perf_counter()
    deadline = started + timeout
    output.mkdir(parents=True, exist_ok=True)
    if method == 'joint':
        parts = [solve(qk, target_path, output / 'all', depth, deadline)]
    else:
        factors = local_circuits(qk.QASMparser(str(target_path)))
        parts = []
        for i, factor in enumerate(factors):
            path = output / f'q{i}.qasm'
            write_qasm(path, [factor])
            parts.append(solve(qk, path, output / f'q{i}', depth, deadline))
            if parts[-1]['status'] != 'COMPLETE':
                break
    complete = all(p['status'] == 'COMPLETE' for p in parts)
    report = dict(method=method, depth=depth, parts=parts,
                  status='COMPLETE' if complete else parts[-1]['status'],
                  solver_s=sum(p['solver_s'] for p in parts),
                  encoding_and_setup_s=sum(p['encoding_and_setup_s'] for p in parts),
                  wall_s=time.perf_counter() - started,
                  validated=complete and all(p['validated'] for p in parts))
    if complete:
        report['fidelity'] = math.prod(p['matrix_fidelity'] for p in parts)
    (output / 'result.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=PRODUCT_CASES, default=None)
    parser.add_argument('--qubits', type=int, help='Generate a larger independent-wire target')
    parser.add_argument('--gates-per-qubit', type=int, default=6)
    parser.add_argument('--seed', type=int, default=20261022)
    parser.add_argument('--resume', action='store_true',
                        help='Keep validated completed runs and retry incomplete runs')
    parser.add_argument('--depths', type=int, nargs='+', default=[2, 4, 6, 7])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=None,
                        help='Budget per method per repetition (default: config TIMEOUT)')
    args = parser.parse_args()
    if args.qubits is not None and (args.qubits < 1 or args.target is not None):
        parser.error('--qubits must be positive and cannot be combined with --target')
    if args.gates_per_qubit < 1:
        parser.error('--gates-per-qubit must be positive')
    if args.qubits is None:
        args.target = args.target or 'independent_rot2'
    else:
        args.target = f'local_random_n{args.qubits}_g{args.gates_per_qubit}_s{args.seed}'
    if any(d < 0 for d in args.depths) or args.repeats < 1 or (args.timeout is not None and args.timeout <= 0):
        parser.error('Depths must be nonnegative; repeats and timeout must be positive')
    root = HERE / 'outputs/fixed_depth' / args.target
    configure_environment(None, root)
    args.timeout = resolve_timeout(args.timeout)
    qk = load_quokka('syn')
    if args.resume:
        previous = json.loads((root / 'results.json').read_text())['config']
        for key in ('target', 'qubits', 'gates_per_qubit', 'seed', 'depths', 'repeats'):
            if previous.get(key) != getattr(args, key):
                parser.error(f'Cannot resume with changed {key}; use the original experiment settings')
        if root.is_symlink():
            parser.error('Output directory must not be a symlink')
    else:
        prepare_output_directory(root)
    target = root / 'target.qasm'
    if args.qubits is None:
        target.write_text((HERE / 'circuits' / f'{args.target}.qasm').read_text())
    else:
        fixture = HERE / 'circuits' / f'{args.target}.qasm'
        generated_target(fixture, args.qubits, args.gates_per_qubit, args.seed)
        target.write_text(fixture.read_text())
    results = []
    for depth in args.depths:
        for repeat in range(args.repeats):
            methods = ('joint', 'separate') if repeat % 2 == 0 else ('separate', 'joint')
            pair = {}
            for method in methods:
                folder = root / f'd{depth}' / f'repeat{repeat}' / method
                saved = folder / 'result.json'
                result = json.loads(saved.read_text()) if args.resume and saved.exists() else None
                reused = result is not None and result.get('validated') and result.get('status') == 'COMPLETE'
                if not reused:
                    prepare_output_directory(folder)
                    result = run_method(qk, target, folder, depth, args.timeout, method)
                    result['budget_s'] = args.timeout
                result.setdefault('budget_s', previous['timeout'] if reused else args.timeout)
                result['repeat'] = repeat
                saved.write_text(json.dumps(result, indent=2))
                pair[method] = result
                results.append(result)
                print(f'{args.target} d={depth} repeat={repeat} {method}: '
                      f'{result["status"]}{" (reused)" if reused else ""}, solver={result["solver_s"]:.3f}s, '
                      f'F={result.get("fidelity")}', flush=True)
            if all(r['validated'] for r in pair.values()):
                assert math.isclose(pair['joint']['fidelity'], pair['separate']['fidelity'],
                                    rel_tol=1e-8, abs_tol=1e-14)
            (root / 'results.json').write_text(json.dumps(dict(config=vars(args), runs=results), indent=2))
    print('\nDepth  Joint solver median  Separate solver median  Joint / separate')
    for depth in args.depths:
        groups = {m: [r for r in results if r['depth'] == depth and r['method'] == m]
                  for m in ('joint', 'separate')}
        if not all(r['validated'] for group in groups.values() for r in group):
            print(f'{depth:5d}  Incomplete/invalid runs: see results.json')
            continue
        joint, separate = (statistics.median(r['solver_s'] for r in groups[m])
                           for m in ('joint', 'separate'))
        print(f'{depth:5d}  {joint:19.4f}  {separate:22.4f}  {joint/separate:16.2f}')


if __name__ == '__main__':
    main()
