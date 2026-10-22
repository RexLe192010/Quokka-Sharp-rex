OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
// Extend local_rot2 by an independent Rz(pi/3) on q2.
// The three pi/4 approximations have combined fidelity cos(pi/24)^6,
// approximately 0.949755. Try --syn-fidelity 0.94 first.
rx(pi/3) q[0];
ry(pi/3) q[1];
rz(pi/3) q[2];
