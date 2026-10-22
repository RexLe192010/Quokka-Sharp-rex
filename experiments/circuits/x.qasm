OPENQASM 2.0;
// Import standard gates, including Hadamard (h), Pauli-X (x), and CNOT (cx).
include "qelib1.inc";
// One-qubit Pauli-X circuit (quantum bit flip).
qreg q[1];
// X swaps |0> and |1>. More generally:
// alpha|0> + beta|1> becomes beta|0> + alpha|1>.
x q[0];
// The verification experiment checks that input |0> produces |1> with certainty.
// X and H are not equivalent: X|0> = |1>, whereas H|0> = |+>.
// No measurement instruction is included; the Python experiment sets the query.
