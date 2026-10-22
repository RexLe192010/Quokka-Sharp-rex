"""Local-gate synthesis examples with independent matrix checks."""
import cmath
import json
import math
import time
from types import SimpleNamespace
from unittest.mock import patch


def multiply(left, right):
    """Ordinary 2x2 matrix multiplication, independent of the CNF encoder."""
    return [[sum(left[i][k] * right[k][j] for k in range(2))
             for j in range(2)] for i in range(2)]


CIRCUIT_CASES = tuple(f'{family}{n}' for family in ('ct', 'mix') for n in range(2, 6))

ROTATION_CASES = ('rz_pi7', 'rx_pi4', 'rx_pi3')


def local_circuits(circuit):
    """Split a unitary containing only supported one-qubit gates; reject couplings."""
    factors = [SimpleNamespace(n=1, circ=[]) for _ in range(circuit.n)]
    for gate in circuit.circ:
        rotation = gate[0] in {'rx', 'ry', 'rz'} and len(gate) == 3
        fixed = gate[0] in {'id', 'h', 's', 'sdg', 't', 'tdg'} and len(gate) == 2
        if not (rotation or fixed):
            raise ValueError(f'Expected single-qubit gates only, got {gate}')
        qubit = gate[-1]
        if not isinstance(qubit, int) or not 0 <= qubit < circuit.n:
            raise ValueError(f'Invalid qubit in {gate}')
        factors[qubit].circ.append([*gate[:-1], 0])
    return factors


def rotation_matrix(axis, angle):
    """Rx/Ry/Rz matrices in computational basis, using radians."""
    c, s = math.cos(angle / 2), math.sin(angle / 2)
    if axis == 'rx':
        return [[c, -1j*s], [-1j*s, c]]
    if axis == 'ry':
        return [[c, -s], [s, c]]
    if axis == 'rz':
        return [[cmath.exp(-1j*angle/2), 0], [0, cmath.exp(1j*angle/2)]]
    raise ValueError(f'Unsupported rotation: {axis}')


def circuit_matrix(circuit):
    """Dense matrix of a small local-gate circuit; q[0] is the leftmost factor."""
    if circuit.n != 1:
        # Dense validation is deliberately limited to small experiments.
        if not 1 <= circuit.n <= 6:
            raise ValueError('Dense matrix validation supports 1–6 qubits')
        import numpy as np
        unit = np.eye(1, dtype=complex)
        for factor in local_circuits(circuit):
            unit = np.kron(unit, circuit_matrix(factor))
        return unit
    unit = [[1, 0], [0, 1]]
    h = 1 / math.sqrt(2)
    matrices = {
        'id': unit, 'h': [[h, h], [h, -h]],
        's': [[1, 0], [0, 1j]], 'sdg': [[1, 0], [0, -1j]],
        't': [[1, 0], [0, cmath.exp(1j * math.pi / 4)]],
        'tdg': [[1, 0], [0, cmath.exp(-1j * math.pi / 4)]],
    }
    for gate in circuit.circ:
        if gate[0] in {'rx', 'ry', 'rz'} and len(gate) == 3 and gate[2] == 0:
            matrix = rotation_matrix(gate[0], float(gate[1]))
        elif len(gate) == 2 and gate[1] == 0 and gate[0] in matrices:
            matrix = matrices[gate[0]]
        else:
            raise ValueError(f'Unsupported one-qubit gate: {gate}')
        unit = multiply(matrix, unit)
    return unit


def unitary_fidelity(target, unit):
    """Normalized squared Hilbert-Schmidt overlap, insensitive to global phase."""
    dimension = len(target)
    if len(unit) != dimension:
        raise ValueError('Target and candidate dimensions differ')
    trace = sum(complex(target[i][j]).conjugate() * unit[i][j]
                for i in range(dimension) for j in range(dimension))
    return float(abs(trace) ** 2 / dimension**2)


def matrix_fidelity(circuit, angle, axis='rz'):
    """Compatibility helper for the earlier single-rotation examples."""
    return unitary_fidelity(rotation_matrix(axis, angle), circuit_matrix(circuit))


def synthesize_circuit(qk, target_path, output, fidelity=0.99, timeout=None, label=None):
    """Search increasing template depths; retain and validate any returned candidate."""
    started = time.perf_counter()
    target = qk.QASMparser(str(target_path))
    target_unitary = circuit_matrix(target)
    target_factors = [circuit_matrix(c) for c in local_circuits(target)]
    target_gates = len(target.circ)
    single_rotation = target_gates == 1 and target.circ[0][0] in {'rx', 'ry', 'rz'}
    axis = target.circ[0][0] if single_rotation else None
    angle = float(target.circ[0][1]) if single_rotation else None
    label = label or ((target_path.stem.replace('_pi', '(pi/') + ')')
                      if single_rotation else target_path.stem)
    target.dagger()
    print(f'Target: {label}; gates: H, S/Sdg, T/Tdg; requested process fidelity: {fidelity}')
    print('Encode the target inverse, then add gate-choice layers and cyclic boundaries.')
    print('Each iteration writes a CNF, runs maxT, and decodes its gate assignment.')
    # Full Pauli cyclic overlap / 4**n is process fidelity.
    # Generator-only (onehot_xz) scores are unsuitable for this fidelity target.
    encoding_started = time.perf_counter()
    cnf = qk.QASM2CNF(target, computational_basis=False)
    encoding_s = time.perf_counter() - encoding_started
    from quokka_sharp import config as qc
    # This checkout overrides the printing argument with CONFIG['DEBUG'].
    # Enable progress only for this call; leave config.local.json unchanged.
    synthesis_started = time.perf_counter()
    with patch.dict(qc.CONFIG, DEBUG=True, TIMEOUT=timeout or qc.CONFIG['TIMEOUT']):
        status, score, qasm, depth = qk.Synthesis(
            cnf, cnf_file_root=str(output), gate_set={'h', 's', 't', 'tdg'},
            fidelity_threshold=fidelity, onehot_xz=False, printing=True)
    synthesis_s = time.perf_counter() - synthesis_started
    print(f'Status: {status}; returned score: {score}; search depth: {depth}')
    report = dict(status=status, target=label, target_gates=target_gates, axis=axis, angle_radians=angle,
                  timeout_s=timeout or qc.CONFIG['TIMEOUT'], requested_fidelity=fidelity,
                  solver_score=str(score), search_depth=depth, qubits=target.n,
                  encoding_s=encoding_s, synthesis_s=synthesis_s)
    if qasm:
        path = output / 'synthesized.qasm'
        path.write_text(qasm)
        circuit = qk.QASMparser(str(path))
        measured = unitary_fidelity(target_unitary, circuit_matrix(circuit))
        candidate_factors = local_circuits(circuit)
        local_scores = [unitary_fidelity(a, circuit_matrix(b)) for a, b in
                        zip(target_factors, candidate_factors)]
        product = math.prod(local_scores)
        agrees = abs(measured - float(score)) < 1e-9
        meets = measured + 1e-12 >= fidelity
        report.update(matrix_fidelity=measured, score_agrees=agrees,
                      meets_threshold=meets, candidate_gates=len(circuit.circ),
                      candidate_parallel_depth=max(len(c.circ) for c in candidate_factors),
                      local_fidelities=local_scores, product_fidelity=product,
                      validated_success=status == 'FOUND' and meets and agrees
                      and abs(product - measured) < 1e-9)
        print(f'Independent matrix fidelity: {measured:.12f}; meets threshold: {meets}')
        if status != 'FOUND':
            print('Search did not finish successfully. Saved QASM is only a candidate;')
            print('the reported search depth may exceed the candidate gate count.')
        print(qasm)
        if not agrees:
            print('WARNING: matrix fidelity disagrees with the solver score.')
    else:
        report['validated_success'] = False
        print('No candidate circuit was returned.')
    report['wall_s'] = time.perf_counter() - started
    (output / 'result.json').write_text(json.dumps(report, indent=2))
    return report
