OPENQASM 2.0;
include "qelib1.inc";
qreg q[1];
// RX(theta) = [[cos(theta/2), -i sin(theta/2)], [-i sin(theta/2), cos(theta/2)]].
// Target the complete unitary, not only its action on |0>.
// pi/4 has an exact short Clifford+T construction; pi/3 and pi/7 test approximation.
rx(pi/4) q[0];
