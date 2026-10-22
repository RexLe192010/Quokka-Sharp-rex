OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
// Two independent rotations: Rx(pi/3) on q0, Ry(pi/3) on q1.
// Approximating each by its pi/4 rotation gives local fidelity cos(pi/24)^2.
// The two-qubit fidelity is cos(pi/24)^4, approximately 0.966216.
// Try --syn-fidelity 0.96 before the harder default threshold 0.99.
rx(pi/3) q[0];
ry(pi/3) q[1];
