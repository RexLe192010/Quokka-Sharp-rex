OPENQASM 2.0;
include "qelib1.inc";
qreg q[1];
// One-qubit 5-gate target, listed in execution order.
// Matrix order is reversed: U = G_last ... G_first.
// Exact Clifford+T control; already expressible in the synthesis library.
// Change basis with H.
h q[0];
// Apply a pi/4 Z-phase (up to global phase).
t q[0];
// The first three gates now implement Rx(pi/4), up to phase.
h q[0];
// Add a Z-phase after the X rotation; order matters.
t q[0];
// Apply another basis change; the target is the entire five-gate unitary.
h q[0];
