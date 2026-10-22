OPENQASM 2.0;
// Import standard gates, including Hadamard (h), Pauli-X (x), and CNOT (cx).
include "qelib1.inc";
// Two Hadamard gates on the same qubit implement identity: H * H = I.
qreg q[1];
// For input |0>, the first H creates |+> = (|0> + |1>)/sqrt(2).
h q[0];
// The second H maps |+> back to |0> by interference.
h q[0];
// This circuit preserves EVERY input state, not only |0>.
// The equivalence experiment compares it with identity.qasm.
// No measurement instruction is included; the Python experiment sets the query.
