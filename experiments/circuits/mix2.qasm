OPENQASM 2.0;
include "qelib1.inc";
qreg q[1];
// One-qubit 2-gate target, listed in execution order.
// Matrix order is reversed: U = G_last ... G_first.
// Mixed-axis approximation target with non-Clifford rotation angles.
// Rotate by pi/4 around X.
rx(pi/4) q[0];
// Then rotate by pi/3 around Y; these rotations do not commute.
ry(pi/3) q[0];
