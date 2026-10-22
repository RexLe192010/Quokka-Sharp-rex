"""Small, editable experiments against this checkout's Quokka# source."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def parse_arguments():
    """Select an experiment and an optional solver configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment', choices=EXPERIMENTS)
    parser.add_argument('--config', type=Path, help='Solver configuration JSON')
    parser.add_argument('--show-cnf', action='store_true',
                        help='Print complete CNF files (encode only)')
    parser.add_argument('--syn-fidelity', type=float, default=None,
                        help='Requested process fidelity for syn (default: 0.99)')
    from synthesis_example import ROTATION_CASES, CIRCUIT_CASES
    from product_synthesis import PRODUCT_CASES
    parser.add_argument('--syn-target', choices=ROTATION_CASES + CIRCUIT_CASES + PRODUCT_CASES, default=None,
                        help='Named synthesis target (default: rz_pi7)')
    parser.add_argument('--syn-mode', choices=['joint', 'separate', 'compare'], default=None,
                        help='Multi-qubit local targets only (default: compare)')
    parser.add_argument('--syn-timeout', type=int, default=None,
                        help='Total synthesis timeout in seconds; overrides config for this run')
    parser.add_argument('--syn-axis', choices=['rx', 'ry', 'rz'],
                        help='Custom rotation axis (default: rz when --syn-angle is given)')
    parser.add_argument('--syn-angle', help='Angle in radians, e.g. "pi/7", "2*pi/3", "0.42"')
    args = parser.parse_args()
    if args.syn_mode is not None and (args.experiment != 'syn' or args.syn_target not in PRODUCT_CASES):
        parser.error('--syn-mode requires syn with an independent multi-qubit target')
    args.syn_angle_value = None
    if args.syn_axis is not None or args.syn_angle is not None:
        if args.experiment != 'syn':
            parser.error('--syn-axis and --syn-angle require syn')
        if args.syn_target is not None:
            parser.error('Use either --syn-target or custom --syn-axis/--syn-angle')
        if args.syn_angle is None:
            parser.error('--syn-axis requires --syn-angle')
        from angles import parse_angle
        try:
            args.syn_angle_value = parse_angle(args.syn_angle)
        except ValueError as error:
            parser.error(str(error))
    if args.syn_target is not None or args.syn_timeout is not None:
        if args.experiment != 'syn':
            parser.error('--syn-target and --syn-timeout require syn')
    if args.syn_timeout is not None and args.syn_timeout <= 0:
        parser.error('--syn-timeout must be positive')
    if args.syn_fidelity is not None:
        if args.experiment != 'syn' or not 0 < args.syn_fidelity < 1:
            parser.error('--syn-fidelity requires syn and a value strictly between 0 and 1')
    if args.show_cnf and args.experiment != 'encode':
        parser.error('--show-cnf is only supported for encode')
    return parser, args


def configure_environment(config_path, output):
    """Set configuration and temporary paths before importing Quokka#."""
    if sys.version_info < (3, 10):
        raise ValueError('This checkout requires Python 3.10+. See README.md for environment setup.')

    environment_config = os.environ.get('QUOKKA_CONFIG')
    config = config_path or (
        Path(environment_config) if environment_config else HERE / 'config.local.json'
    )
    if config_path or environment_config or config.exists():
        if not config.is_file():
            raise ValueError(f'Configuration does not exist: {config}')
        os.environ['QUOKKA_CONFIG'] = str(config.resolve())

    # Low-level default arguments capture this directory at import time.
    tempfile.tempdir = str(output)
    # Load the working source so edits take effect without reinstalling.
    sys.path.insert(0, str(HERE.parent / 'quokka_sharp'))


def resolve_timeout(override=None):
    """Resolve a timeout after configure_environment has selected the config."""
    from quokka_sharp import config as qc
    value = qc.CONFIG['TIMEOUT'] if override is None else override
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError('TIMEOUT must be a positive number')
    import math
    if not math.isfinite(value):
        raise ValueError('TIMEOUT must be finite')
    return value


def load_quokka(experiment):
    """Import the local library and check the selected experiment's solver."""
    try:
        import quokka_sharp as qk
    except ModuleNotFoundError as error:
        raise ValueError(
            f'Missing dependency: {error.name}. Follow the environment setup in README.md.'
        ) from error
    from quokka_sharp import config as qc

    if experiment != 'encode':
        key = 'D4ToolInvocation' if experiment == 'syn' else 'ToolInvocation'
        executable = qc.CONFIG[key].split(' ')[0]
        if not shutil.which(executable):
            raise ValueError(
                f'Solver not found: {executable}. Set {key} in config.local.json; see README.md.'
            )
    return qk


def prepare_output_directory(output):
    """Replace this experiment's previous artifacts after preflight succeeds."""
    if output.is_symlink():
        raise ValueError(f'Output directory must not be a symlink: {output}')
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def load_circuit(qk, name):
    """Read a named QASM fixture from circuits/."""
    return qk.QASMparser(str(HERE / 'circuits' / f'{name}.qasm'))


def encode_circuit(qk, circuit, computational=False):
    """Encode a parsed circuit with the configured counting backend's format."""
    from quokka_sharp import config as qc

    return qk.QASM2CNF(
        circuit,
        computational_basis=computational,
        ganak=qc.CONFIG.get('GanakEncoding', False),
    )


def run_encoding(qk, output, show_cnf=False):
    """Compare the base HH encoding with different equivalence-query boundaries."""
    from quokka_sharp.eq import basis, identity_check

    cnf = encode_circuit(qk, load_circuit(qk, 'hh'))
    base = output / 'hh_base.cnf'
    cnf.write_to_file(str(base))
    queries = [
        ('base circuit', base),
        ('Z_0 boundary', basis(0, True, cnf, str(output))),
        ('X_0 boundary', basis(0, False, cnf, str(output))),
        ('cyclic identity', identity_check(cnf, str(output))),
        ('cyclic linear identity', identity_check(cnf, str(output), constrain_2n=True)),
    ]
    for label, path in queries:
        contents = Path(path).read_text()
        if show_cnf:
            print(f'\n--- {label} ---')
            print(contents.rstrip())
        else:
            print(f'{label}: {contents.splitlines()[0]}')
    print('These are encodings only; no equivalence result has been computed.')


def run_simulation(qk, output):
    """Compute the Bell circuit's probability of measuring 00 from input 00."""
    cnf = encode_circuit(qk, load_circuit(qk, 'bell'), computational=True)
    cnf.leftProjectAllZero()
    cnf.add_measurement({0: 0, 1: 0})
    probability = qk.Simulate(cnf, cnf_file_root=str(output))
    print('P(Bell output = 00):', probability, '(expected 0.5)')


def run_verification(qk, output):
    """Check that X maps input 0 to output 1, and does not preserve 0."""
    # Verify uses the temporary output directory configured before import.
    for final_bit, expected in [(1, True), (0, False)]:
        cnf = encode_circuit(qk, load_circuit(qk, 'x'), computational=True)
        result = qk.Verify(cnf, {0: 0}, {0: final_bit})
        print(f'X: |0> -> |{final_bit}>: {result} (expected {expected})')


def run_equivalence(qk, output):
    """Compare equivalent and inequivalent pairs using three Pauli checks."""
    pairs = [('hh', 'identity', True), ('h', 'x', False)]
    for left, right, expected in pairs:
        combined = load_circuit(qk, left)
        inverse = load_circuit(qk, right)
        inverse.dagger()
        combined.append(inverse)
        for check in ['cyclic', 'linear', 'cyclic_linear']:
            cnf = encode_circuit(qk, combined)
            result = qk.CheckEquivalence(cnf, cnf_file_root=str(output), check=check, N=1)
            print(f'{left} vs {right}, {check}: {result} (expected {expected})')


def run_synthesis(qk, output, fidelity=0.99, target="rz_pi7", timeout=None,
                  axis=None, angle=None, angle_expression=None, mode=None):
    """Synthesize a named or custom rotation and show the depth search."""
    from synthesis_example import synthesize_circuit
    path = HERE / 'circuits' / f'{target}.qasm'
    from product_synthesis import PRODUCT_CASES, run_product_synthesis
    if target in PRODUCT_CASES:
        return run_product_synthesis(qk, path, output, fidelity, timeout, mode or 'compare')
    label = None
    if angle is not None:
        axis = axis or 'rz'
        label = f'{axis}({angle_expression})'
        path = output / 'target.qasm'
        # Write the evaluated finite number; never inject user expressions into QASM.
        path.write_text('OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[1];\n'
                        f'// Custom angle in radians.\n{axis}({angle!r}) q[0];\n')
    synthesize_circuit(qk, path, output, fidelity, timeout, label=label)


EXPERIMENTS = {
    'encode': run_encoding,
    'sim': run_simulation,
    'verify': run_verification,
    'eq': run_equivalence,
    'syn': run_synthesis,
}


def main():
    parser, args = parse_arguments()
    output = HERE / 'outputs' / args.experiment
    if args.experiment == 'syn' and args.syn_target not in (None, 'rz_pi7'):
        output = HERE / 'outputs/syn_cases' / args.syn_target
    if args.syn_angle is not None:
        output = HERE / 'outputs/syn_custom' / (args.syn_axis or 'rz')
    try:
        configure_environment(args.config, output)
        qk = load_quokka(args.experiment)
        prepare_output_directory(output)
    except ValueError as error:
        parser.error(str(error))
    options = {'show_cnf': args.show_cnf} if args.experiment == 'encode' else {}
    if args.experiment == 'syn' and args.syn_fidelity is not None:
        options['fidelity'] = args.syn_fidelity
    if args.experiment == 'syn':
        options.update(target=args.syn_target or 'rz_pi7', timeout=args.syn_timeout,
                       axis=args.syn_axis, angle=args.syn_angle_value,
                       angle_expression=args.syn_angle, mode=args.syn_mode)
    EXPERIMENTS[args.experiment](qk, output, **options)


if __name__ == '__main__':
    main()
