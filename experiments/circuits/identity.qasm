OPENQASM 2.0;
// Import standard gates, including Hadamard (h), Pauli-X (x), and CNOT (cx).
include "qelib1.inc";
// Identity circuit: a qubit register with no gates applied.
qreg q[1];
// Every input state is unchanged: alpha|0> + beta|1> stays the same.
// For input |0>, a computational-basis measurement returns 0 with certainty.
// This is the reference circuit for checking H followed by H.
// No measurement instruction is included; the Python experiment sets the query.
