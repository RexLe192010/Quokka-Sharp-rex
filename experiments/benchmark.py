"""Bounded, reproducible larger experiments using Quokka#'s public APIs."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

import psutil
from profiling import Profiler
from run import HERE, configure_environment, load_quokka, prepare_output_directory, resolve_timeout

CASES = {'eq': ('ghz5', 'clifford_t4', 'qft2', 'qft8'),
         'syn': ('bell2', 'swap2', 'ghz3')}


def circuit_text(case):
    """Use fixed seeds and retain the exact input in the output directory."""
    if case.startswith('qft'):
        n = int(case[3:])
        path = HERE.parent.parent / 'quokka-sharp-artifacts/benchmark/algorithm/origin' / f'qft_nativegates_ibm_qiskit_opt0_{n}.qasm'
        return path.read_text(), str(path)
    if case == 'clifford_t4':
        n, gates, rng = 4, [], random.Random(20261020)
        for layer in range(4):
            for q in range(n):
                gates.append(f'{rng.choice(["h", "t", "tdg", "s"])} q[{q}];')
            gates.append(f'cx q[{layer % n}],q[{(layer + 1) % n}];')
    elif case == 'swap2':
        n, gates = 2, ['cx q[0],q[1];', 'cx q[1],q[0];', 'cx q[0],q[1];']
    else:
        n = 2 if case == 'bell2' else int(case[3:])
        gates = ['h q[0];'] + [f'cx q[{i-1}],q[{i}];' for i in range(1, n)]
    return 'OPENQASM 2.0;\ninclude "qelib1.inc";\n' + f'qreg q[{n}];\n' + '\n'.join(gates) + '\n', 'generated; seed=20261020 for clifford_t4'


def encode(qk, circuit, profiler, synthesis=False):
    from quokka_sharp import config as qc
    with profiler.span('circuit_encoding'):
        return qk.QASM2CNF(circuit, computational_basis=False,
                          ganak=False if synthesis else qc.CONFIG.get('GanakEncoding', False))


def equivalence(qk, first, second, output, profiler, check):
    with profiler.span('compose'):
        combined = copy.deepcopy(first)
        inverse = copy.deepcopy(second)
        inverse.dagger()
        combined.append(inverse)
    cnf = encode(qk, combined, profiler)
    with profiler.span('equivalence_overhead'):
        return qk.CheckEquivalence(cnf, cnf_file_root=str(output), check=check, N=1)


def run_eq(qk, target, text, args, output, profiler):
    # HH is an identity; a final X makes a guaranteed non-equivalent unitary.
    suffix = 'h q[0];\nh q[0];\n' if args.variant == 'same' else 'x q[0];\n'
    path = output / 'comparison.qasm'
    path.write_text(text.rstrip() + '\n' + suffix)
    with profiler.span('parse'):
        comparison = qk.QASMparser(str(path))
    result = equivalence(qk, target, comparison, output, profiler, args.check)
    expected = args.variant == 'same'
    return dict(result=result, expected=expected,
                status=('PASS' if result == expected else 'MISMATCH') if isinstance(result, bool) else str(result))


def run_syn(qk, target, args, output, profiler):
    with profiler.span('compose'):
        inverse = copy.deepcopy(target)
        inverse.dagger()
    cnf = encode(qk, inverse, profiler, synthesis=True)
    with profiler.span('synthesis_overhead'):
        status, score, qasm, depth = qk.Synthesis(
            cnf, cnf_file_root=str(output), gate_set={'h', 'cx', 's'},
            fidelity_threshold=1, onehot_xz=True)
    report = dict(status=status, score=str(score), depth=depth)
    if qasm and status == 'FOUND':
        path = output / 'synthesized.qasm'
        path.write_text(qasm)
        # Verification is deliberately reported separately from synthesis cost.
        validation = output / 'validation'
        validation.mkdir()
        # Leave outer instrumentation before starting the separate validation profile.
        report['validation_pending'] = True
    return report


def worker(args, output):
    configure_environment(args.config, output)
    qk = load_quokka(args.function)
    if args.function == 'syn':
        load_quokka('eq')
    from quokka_sharp import config as qc
    qc.CONFIG['TIMEOUT'] = args.timeout
    prepare_output_directory(output)
    profiler, report = Profiler(), {}
    try:
        text, origin = circuit_text(args.case)
        source = output / 'target.qasm'
        source.write_text(text)
        report.update(case=args.case, function=args.function,
                      check=args.check if args.function == 'eq' else 'onehot_xz',
                      variant=args.variant if args.function == 'eq' else None, origin=origin,
                      input_sha256=hashlib.sha256(text.encode()).hexdigest(),
                      solver_timeout_s=args.timeout, config=dict(qc.CONFIG))
        with profiler.instrument():
            with profiler.span('parse'):
                target = qk.QASMparser(str(source))
            report.update(qubits=target.n, gates=len(target.circ))
            operation = run_eq if args.function == 'eq' else run_syn
            if args.function == 'eq':
                report.update(operation(qk, target, text, args, output, profiler))
            else:
                report.update(operation(qk, target, args, output, profiler))
        if report.pop('validation_pending', False):
            verifier = Profiler()
            validation = output / 'validation'
            with verifier.instrument():
                with verifier.span('parse'):
                    synthesized = qk.QASMparser(str(output / 'synthesized.qasm'))
                verified = equivalence(qk, target, synthesized, validation, verifier, 'linear')
            verifier.save(validation)
            report['independent_equivalence'] = verified
            report['status'] = 'PASS' if verified is True else 'VALIDATION_FAILED'
    except Exception as error:
        report.update(status='ERROR', error=f'{type(error).__name__}: {error}')
    finally:
        profiler.save(output)
        (output / 'result.json').write_text(json.dumps(report, indent=2, default=str))
    return 0 if report.get('status') == 'PASS' else 1


def terminate_worker(proc):
    """Eq solvers have their own sessions, so also kill descendant processes."""
    try:
        children = psutil.Process(proc.pid).children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def supervise(args, case, variant):
    """Fresh Python process per experiment, with total wall and RSS limits."""
    name = f'{case}-{args.check}-{variant}' if args.function == 'eq' else case
    output = HERE / 'outputs/benchmarks' / args.function / name
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), args.function,
               '--case', case, '--variant', variant, '--check', args.check,
               '--timeout', str(args.timeout), '--worker']
    if args.config:
        command += ['--config', str(args.config.resolve())]
    # Fail before launching a worker if OS permissions prohibit memory profiling.
    psutil.Process().children(recursive=True)
    prepare_output_directory(output)
    started_ns = time.time_ns()
    start, peak, stopped = time.perf_counter(), 0, None
    # Console chatter from upstream goes to a fixed log, not the terminal.
    log_path = output.parent / f'{name}.log'
    with log_path.open('w') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while proc.poll() is None:
                try:
                    tree = [psutil.Process(proc.pid)] + psutil.Process(proc.pid).children(recursive=True)
                    rss = sum(p.memory_info().rss for p in tree if p.is_running()) / 1024**2
                    peak = max(peak, rss)
                except psutil.Error:
                    pass
                if time.perf_counter() - start > args.wall_timeout:
                    stopped = 'WALL_TIMEOUT'
                elif peak > args.memory_mib:
                    stopped = 'MEMORY_LIMIT'
                if stopped:
                    terminate_worker(proc)
                    break
                time.sleep(.01)
        finally:
            if proc.poll() is None:
                terminate_worker(proc)
    output.mkdir(parents=True, exist_ok=True)
    supervision = dict(status=stopped or ('COMPLETED' if proc.returncode == 0 else 'FAILED'),
                       elapsed_s=time.perf_counter()-start, sampled_tree_peak_rss_mib=peak,
                       returncode=proc.returncode, wall_limit_s=args.wall_timeout,
                       memory_limit_mib=args.memory_mib)
    (output / 'supervision.json').write_text(json.dumps(supervision, indent=2))
    result_path = output / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() and result_path.stat().st_mtime_ns >= started_ns and not stopped else {}
    print(f'{name}: {stopped or result.get("status", "ERROR")} | {supervision["elapsed_s"]:.3f}s | tree RSS {peak:.1f} MiB')
    if result.get('error'):
        print(' ', result['error'])
    return proc.returncode == 0 and not stopped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('function', choices=CASES)
    parser.add_argument('--case', default=None, help='Case name, or all')
    parser.add_argument('--check', choices=['linear', 'cyclic', 'cyclic_linear'], default='cyclic_linear')
    parser.add_argument('--variant', choices=['same', 'different', 'both'], default='both')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--timeout', type=int, default=None, help='Quokka solver timeout (default: config TIMEOUT)')
    parser.add_argument('--wall-timeout', type=float, default=None, help='Total seconds per experiment (default: twice solver timeout)')
    parser.add_argument('--memory-mib', type=float, default=2048)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.list:
        print(', '.join(CASES[args.function]))
        return 0
    args.case = args.case or CASES[args.function][0]
    if args.case not in (*CASES[args.function], 'all'):
        parser.error('Unknown case; use --list')
    config_output = HERE / 'outputs/benchmarks'
    if args.worker:
        worker_name = f'{args.case}-{args.check}-{args.variant}' if args.function == 'eq' else args.case
        config_output = config_output / args.function / worker_name
    configure_environment(args.config, config_output)
    args.timeout = resolve_timeout(args.timeout)
    if int(args.timeout) != args.timeout:
        parser.error('TIMEOUT must be a positive whole number of seconds')
    args.timeout = int(args.timeout)
    if args.wall_timeout is None:
        args.wall_timeout = 2 * args.timeout
    if min(args.timeout, args.wall_timeout, args.memory_mib) <= 0:
        parser.error('Timeouts and memory limit must be positive')
    if args.worker:
        name = f'{args.case}-{args.check}-{args.variant}' if args.function == 'eq' else args.case
        return worker(args, HERE / 'outputs/benchmarks' / args.function / name)
    cases = CASES[args.function] if args.case == 'all' else [args.case]
    variants = ['same', 'different'] if args.function == 'eq' and args.variant == 'both' else [args.variant]
    results = [supervise(args, case, variant) for case in cases for variant in variants]
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
