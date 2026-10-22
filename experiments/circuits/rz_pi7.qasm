OPENQASM 2.0;
include "qelib1.inc";
qreg q[1];
// Rz(theta) = diag(exp(-i theta/2), exp(i theta/2)).
// pi/7 is not a Clifford+T elementary rotation (T is Rz(pi/4) up to phase).
// Approximate this complete unitary, not only its action on |0>.
rz(pi/7) q[0];
