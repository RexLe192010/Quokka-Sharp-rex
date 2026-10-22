OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
// Independent circuit on qubit 0.
h q[0];
t q[0];
// Independent circuit on qubit 1.
h q[1];
t q[1];
h q[1];
t q[1];
h q[1];
t q[1];
h q[1];
t q[1];
h q[1];
