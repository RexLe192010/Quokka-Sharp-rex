OPENQASM 2.0;
// Import standard gates, including Hadamard (h), Pauli-X (x), and CNOT (cx).
include "qelib1.inc";
// Prepare the Bell state |Phi+> from the all-zero input |00>.
// In the explanations below, ket positions are ordered as |q[0] q[1]>.
qreg q[2];
// Put q[0] into superposition: |00> -> (|00> + |10>)/sqrt(2).
h q[0];
// Controlled-X: q[0] is the control and q[1] is the target.
// Flip q[1] only when q[0] is 1: |10> -> |11>, while |00> is unchanged.
cx q[0],q[1];
// Final state: (|00> + |11>)/sqrt(2), an entangled state.
// Joint measurement probabilities: P(00)=P(11)=1/2; P(01)=P(10)=0.
// No measurement instruction is included; the Python experiment sets the query.
