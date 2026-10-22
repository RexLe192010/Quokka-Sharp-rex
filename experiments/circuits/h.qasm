OPENQASM 2.0;
// Import standard gates, including Hadamard (h), Pauli-X (x), and CNOT (cx).
include "qelib1.inc";
// One-qubit Hadamard circuit. The simulation example assumes input |0>.
qreg q[1];
// H maps |0> to |+> = (|0> + |1>)/sqrt(2).
// It maps |1> to |-> = (|0> - |1>)/sqrt(2).
h q[0];
// Measuring H|0> in the computational basis gives 0 or 1 with probability 1/2.
// No measurement instruction is included; the Python experiment sets the query.
