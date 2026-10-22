# Quokka# experiments

Small, editable examples using the source in this checkout. Start with `encode`
to explore `eq.py`'s boundary constraints without installing a solver.

## Current local status

| Command | Backend | Status in this workspace |
|---|---|---|
| `encode` / `encode --show-cnf` | None | Ready |
| `sim`, `verify`, `eq` | Existing Ganak binary, mode 7 | Configured and checked on the supplied examples |
| `syn` | Native macOS MaxT build | Configured; approximate Rz(pi/7) example with matrix validation |

Installing the Python package does not install external solver binaries.
Both external backends are now configured locally. Keep `config.local.json`;
copying the generic example over it would discard the working paths.

## Setup

Use Python 3.10 or newer (the current source uses `int | None` annotations).
First enter the experiment directory. From the outer `Quokka#` directory:

```bash
cd Quokka-Sharp/experiments
```

Then create an environment with a compatible Python interpreter:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ../quokka_sharp
```

The runner explicitly imports the local source, so source edits take effect on
the next run.

## Experiments

```bash
python run.py encode
python run.py encode --show-cnf  # print all five complete weighted CNFs
python run.py sim
python run.py verify
python run.py eq
```

Run the locally configured synthesis backend:

```bash
python run.py syn
```

| Experiment | What to inspect | Expected result |
|---|---|---|
| `encode` | Base HH circuit, X/Z boundary queries, cyclic and cyclic-linear CNFs | Five files; prints variable/clause counts; no solver call |
| `sim` | Bell-state measurement probability in computational basis | P(00) = 0.5 |
| `verify` | X with input 0 and output 1 or 0 | True, then False |
| `eq` | HH versus identity; H versus X; three Pauli checking modes | True for HH/identity, False for H/X |
| `syn` | Approximate Rz(pi/7) with H, S/Sdg, T/Tdg and full Pauli cyclic fidelity | Depth-by-depth search toward fidelity 0.99; may time out |

Edit `run_encoding`, `run_simulation`, `run_verification`, `run_equivalence`,
or `run_synthesis` in `run.py` to change parameters or call other functions.
Setup and circuit-loading helpers are separate; `main()` only coordinates setup
and dispatch. Tiny input circuits are in `circuits/`. Expected values are printed
for comparison; this is an exploratory runner, not an automated test suite.

Each experiment reuses `outputs/<experiment>/` (for example, `outputs/eq/`).
After dependency and solver checks succeed, rerunning an experiment removes its
previous output directory and writes fresh files. Only the latest run is kept.
Do not store hand-written files there or run the same experiment concurrently.
Inspect the generated CNFs with a text editor: `p cnf` gives the variable and
clause counts, `c p weight` lines encode weights, and remaining clause lines
encode constraints. Synthesis also writes solver logs and decoded QASM.

## Solver configuration

Only `encode` works without a solver. The other examples require GPMC (or a
compatible WMC backend) for sim/verify/eq, and d4max for synthesis.

Keep the existing `config.local.json` in this workspace: it already configures
Ganak. For a new checkout only, create a configuration if one does not exist:

```bash
[ -f config.local.json ] || cp config.example.json config.local.json
```

The example file contains executable names, not installed solvers. Set
`ToolInvocation` and `GetResult` for your counting backend, and set
`D4ToolInvocation` separately for synthesis. Installing a backend requires
obtaining its executable as well as editing the configuration.

`config.local.json` is loaded automatically. Alternatively use
`python run.py eq --config /absolute/path/to/config.json` or `QUOKKA_CONFIG`.
Priority is explicit `--config`, then `QUOKKA_CONFIG`, then the local file.
The supplied result regex targets GPMC output; another backend requires its
own output regex and invocation arguments. Quokka# currently splits invocation
strings on spaces, so avoid solver paths containing spaces.

The solver timeout is 30 seconds in the example configuration. TIMEOUT or ERROR
outputs are execution outcomes, not evidence that circuits are inequivalent.
The synthesis score with restricted generator checks is not automatically the
same metric as full process fidelity. The `run.py syn` example instead uses full
Pauli cyclic encoding (`onehot_xz=False`) for approximate synthesis.

Generated outputs, the virtual environment, and local config are Git-ignored.

## Local Ganak setup

The local configuration uses the existing `ganak/build-mac/ganak` binary via
`ganak.local`, a symlink that avoids spaces in the executable path. It uses
`--mode=7` (real weighted counting) and the output regex for this build.
The sim, verify, and eq examples have been run successfully with this setup.
`GanakEncoding` selects Ganak's weight format in the experiment runner.

This configuration supports the real-weight examples provided here. If you
add circuits whose computational encoding has complex weights, the solver
mode and weight serialization must also be adapted; changing only the mode
is insufficient for this Ganak version. Pauli encodings use real weights.

## Synthesis on this Mac

A native ARM64 MaxT executable has been built from d4 tag `v0.1.0` in
`../../d4-quokka/build-macos/maxT` (relative to this directory).
`config.local.json` now points `D4ToolInvocation` to its absolute path;
the existing Ganak settings are preserved.

```bash
python run.py syn
```

The target is now `circuits/rz_pi7.qasm`: a one-qubit Rz(pi/7) rotation,
with matrix diag(exp(-i*pi/14), exp(i*pi/14)). The synthesis template selects
H, S/Sdg and T/Tdg gates, a single-qubit Clifford+T gate set. Quokka# enables
S and Sdg together when `s` is selected. The requested process fidelity is 0.99:

```
F(U, S) = |Tr(U† S)|² / 4
```

This is unitary approximation up to global phase, not just preparing the same
state from |0>. We encode the inverse target, add unknown gate-choice layers,
and close the endpoints with the full Pauli cyclic identity query. maxT maximizes
the weighted count over gate choices; division by 4 gives process fidelity.
The generator-only score used by the former H example is not used here.

`run.py syn` prints each depth/iteration, achieved fidelity, and iteration time.
The search starts at depth zero. This checkout ignores its `printing` argument
in favor of `CONFIG['DEBUG']`, so the example temporarily enables that setting
for this call and restores it afterward; your config file is unchanged.

For reference, the identity has fidelity about 0.950484434 and T has fidelity
about 0.971941665 with this target. Neither reaches 0.99. A timeout does not
mean the target cannot be approximated. The script independently computes
the returned candidate's 2x2 matrix and reports whether it meets the threshold.
A timeout candidate is never labelled a validated success.

```bash
# Harder search: default fidelity 0.99
python run.py syn
# Quick successful approximation, typically T at depth 1
python run.py syn --syn-fidelity 0.97
# More demanding; consider increasing TIMEOUT in your local config
python run.py syn --syn-fidelity 0.999
```

The implementation is in `synthesis_example.py`, keeping `run.py` short.
`outputs/syn/` is replaced on rerun and contains per-iteration weighted CNFs,
maxT `.out`/`.err` logs and decoded `.res` candidates. `synthesized.qasm` stores
the returned candidate, even on timeout. Read `result.json` for solver status,
independent matrix fidelity, whether the threshold was met, and
`validated_success`. On timeout, the search depth may exceed the returned
candidate's gate count. Increase `TIMEOUT` for a longer search; increasing the
fidelity requirement can make the search substantially more expensive.

### Rebuild the local solver

The local source includes a macOS build and small portability fixes. From
this `experiments` directory:

```bash
# Only if these build dependencies are missing:
brew install cmake boost gmp

bash ../../d4-quokka/macos/build.sh
python run.py syn
```

Use the macOS build script, not upstream `build.sh`. Details and the source
patch are in `../../d4-quokka/macos/README.md` and `compatibility.patch`.
This is a local port of upstream commit
`c121982c16b8195a617567e41ba3b63742d1edb1`, not an upstream macOS release.
It uses MaxT's existing classic branching mode. PaToH partitioning is excluded
and produces an explicit error if requested; it is not needed by this MaxT
configuration. This example uses real-weight Pauli synthesis; complex-weight
synthesis and other solver configurations are not covered by its validation.

### Configuration and troubleshooting

- Do not overwrite the working `config.local.json` with `config.example.json`.
  The latter is a generic GPMC template, not this machine's Ganak/MaxT setup.
- `D4ToolInvocation` must point to the actual MaxT executable. Its name does
  not have to be `maxT_static`.
- The executable must support `-i`, `--complex`, and `--threshold` and emit
  the assignment/weight format expected by Quokka#. Ganak cannot replace it.
- Paths must not contain spaces with the current invocation parser; use a
  symlink at a path without spaces if needed.
- If the source directory is moved, update the absolute solver paths in
  `config.local.json`. An exported `QUOKKA_CONFIG` overrides that local file.
- Solver logs are saved in `outputs/syn/`. A TIMEOUT or CRASH is not success.

## Larger experiments and component profiling

`benchmark.py` calls the same local `CheckEquivalence` and `Synthesis` APIs as
`run.py`. It adds reproducible inputs, expected-result checks, bounded execution,
and instrumentation; it does not replace Quokka#'s encoding or search algorithm.
Install the extra profiler dependency in the existing virtual environment:

```bash
python -m pip install -r requirements.txt
python benchmark.py eq --list
python benchmark.py syn --list

python benchmark.py eq --case ghz5
python benchmark.py eq --case clifford_t4
python benchmark.py eq --case qft2 --check linear
python benchmark.py eq --case qft2 --check cyclic
python benchmark.py eq --case qft2 --check cyclic_linear
python benchmark.py eq --case qft8 --timeout 30 --wall-timeout 45

python benchmark.py syn --case bell2
python benchmark.py syn --case swap2
python benchmark.py syn --case ghz3
```

Keep your working `config.local.json`; do not overwrite it with the example.
Equivalence uses `ToolInvocation` (currently your Ganak). Synthesis uses
`D4ToolInvocation` (your native maxT) and then `ToolInvocation` to independently
check the returned circuit. `--config PATH` selects another configuration.
Process-memory inspection must be permitted by the OS; the Codex sandbox may
require approval to run these benchmarks outside the sandbox.

| Function | Case | Input |
|---|---|---|
| eq | `ghz5` | Five-qubit GHZ unitary: H followed by a CX chain, 5 gates |
| eq | `clifford_t4` | Four qubits, 20 H/S/T/Tdg/CX gates, fixed seed 20261020 |
| eq | `qft2`, `qft8` | QFT circuits in the sibling artifact checkout, `benchmark/algorithm/origin/` |
| syn | `bell2` | Two-qubit H + CX unitary |
| syn | `swap2` | SWAP specified by three CX gates |
| syn | `ghz3` | Three-qubit H + CX chain unitary |

The artifact checkout is required only for the QFT cases. These are the actual
artifact files, not newly generated MQT-Bench instances. Every run saves its
input QASM and SHA-256. For eq, the default runs two comparisons: append HH
(expected equivalent), and append X (expected non-equivalent). These are
controlled sanity/performance experiments, not a recreation of the paper's full
evaluation. `--variant same` or `--variant different` runs one comparison.
`--check` selects `linear`, `cyclic`, or `cyclic_linear`; the default is
`cyclic_linear`. All cases use the Pauli encoding. `--case all` runs the cases
for the selected functionality, including potentially expensive cases.

Each case runs in a fresh Python process. The solver timeout defaults to config
`TIMEOUT`; the total wall limit (including synthesis validation) defaults to
twice that timeout. The sampled process-tree RSS limit defaults to 2048 MiB. Adjust with `--timeout`, `--wall-timeout`, and
`--memory-mib`. The memory limit is a polling safeguard, not a strict OS memory
quota. Timeouts, errors and unexpected answers produce a nonzero exit code.
QFT8 and non-Clifford circuits may time out; that is a measured outcome, not an
equivalence result. Synthesis targets here are complete unitaries, not just state
preparation from zero.

Outputs are replaced on each rerun of the same case/check/variant:
`outputs/benchmarks/eq/<case>-<check>-<variant>/` or
`outputs/benchmarks/syn/<case>/`. Existing small `run.py` outputs are separate.
Each directory contains:

- `target.qasm`, and `comparison.qasm` for equivalence.
- Full weighted CNF files written by Quokka# (including the synthesis choice
  variable annotations). Synthesis may reuse a filename across search depths;
  the profile records size/counts at each write, while the file is its last version.
- `profile.json`: individual events, including solver commands, CNF variable and
  clause counts, byte sizes, and template depth.
- `phases.csv`: aggregate component timings and memory samples.
- `result.json`: input provenance, configuration, expected/actual result, and
  synthesis score/depth. `PASS` for synthesis requires independent equivalence.
- `supervision.json`: end-to-end time, combined process-tree peak sampled RSS,
  configured limits, and termination status. A forced kill can prevent final
  profiles/results from being written; this file remains authoritative for it.
- For successful synthesis, `synthesized.qasm` and a `validation/` directory with
  separate CNFs and profiles for the independent linear equivalence check.

The parent directory also contains a fixed per-case `.log` with upstream console
output. No timestamped directories accumulate.

### Reading the measurements

| Phase | Work measured |
|---|---|
| `parse` | QASM parsing |
| `compose` | Copying/dagger/composition of circuits |
| `circuit_encoding` | QASM2CNF: fixed gate-by-gate circuit encoding |
| `template_encoding` | Synthesis gate-choice layers (`add_syn_layer`) |
| `query_constraints` | Copying the encoding and adding boundary/identity constraints |
| `cnf_write` | Serializing weighted CNF and writing it to disk |
| `wmc_solver` | Ganak or configured WMC backend, one event per invocation |
| `maxT` | Synthesis backend, one event per invocation |
| `parse_solver_result` | Reading/parsing backend results |
| `decode_qasm` | Turning synthesis choices into gates |
| `equivalence_overhead`, `synthesis_overhead` | Remaining API control flow |

`exclusive_s` excludes nested measured phases; `inclusive_s` includes them.
Do not sum inclusive times. Solver time runs from process launch until result
collection, including launch/polling overhead; it is not solver CPU time. This
runner uses `N=1`, so solver intervals do not overlap. The total supervised time
also includes imports, profiling, reporting, and (for synthesis) validation.

Memory is sampled RSS, not allocated bytes per function. Python RSS is an absolute
process footprint sampled at phase boundaries and every 5 ms while active;
solver RSS is sampled over the solver and its descendants. Parent supervision
samples their combined footprint every 10 ms. Sampling can miss short peaks;
blank solver RSS means no usable sample. RSS values are not additive across
phases, and shared pages can be counted more than once across processes. CNF
bytes/variables/clauses are separate measures of formula size. Very short
operations are affected appreciably by instrumentation overhead.

### Why synthesis resembles equivalence checking

Equivalence fixes two circuits U and V, encodes their composition with an inverse,
and counts an identity-overlap query. Synthesis fixes the target inverse U† but
introduces Boolean choices for gates in an unknown circuit S. For each template
depth, maxT searches the choices that maximize the weighted count over the
remaining circuit-encoding variables:

```
equivalence: evaluate WMC(F(U, V†, identity boundary))
synthesis:   maximize_g WMC_execution(F(S(g), U†, identity boundary))
```

This experiment uses the H/CX/S gate set and `onehot_xz=True`. Its score is the
sum of diagonal Pauli coefficients for the 2n generators Xi and Zi, divided by
2n. Score 1 means all generators are preserved, hence equivalence up to global
phase (subject to the implementation's numerical tolerance). A lower generator
score is not the full cyclic process fidelity.

Quokka# starts with depth zero, adds a symbolic layer when necessary, calls maxT,
and decodes a successful gate assignment to QASM. This is a search over circuits,
which is substantially harder than checking one fixed pair. The first successful
searched depth is relative to this template/gate set; it is not a claim of global
minimum gate count. The runner then checks the synthesized circuit against the
original target using Ganak and the separate Xi/Zi linear queries.

## Representative single-qubit rotation synthesis

Three named rotation targets remain: `rx_pi4` for a short exact construction,
`rx_pi3` for an approximation search, and `rz_pi7` as the default baseline.
All use the same H, S/Sdg, T/Tdg choices and the full Pauli cyclic score.
The independent matrix check uses the target's actual axis and angle.
Other axes and angles are available through the custom-angle options below.

```bash
python run.py syn --syn-target rx_pi4
python run.py syn --syn-target rx_pi3 --syn-fidelity 0.98
python run.py syn --syn-target rz_pi7 --syn-timeout 60
```

The commented QASM targets are in `circuits/`. The Rx targets use fixed output
folders, `outputs/syn_cases/<target>/`; the default Rz target uses `outputs/syn/`.
Rerunning a target replaces its previous files, including when changing fidelity
or timeout. Inspect `result.json`, `synthesized.qasm`, and the per-iteration
`.res` files.

| Angle | Identity fidelity (any axis) | Fidelity of the corresponding pi/4 rotation | Purpose |
|---|---|---|---|
| pi/4 | 0.853553391 | 1 | Short exact constructions using H |
| pi/3 | 0.750000000 | 0.982962913 | Larger initial error; approximate threshold comparison |
| pi/7 | 0.950484434 | 0.971941665 | Compare with the original Rz plateau |

The angle affects overlap; the axis also affects the number of primitive gates
needed in this library. For example, Rx(pi/4) is H T H up to phase. Ry(pi/4)
is S H T H Sdg in matrix-product notation (rightmost gate acts first), hence
QASM order Sdg, H, T, H, S. The same pi/4 constructions give
useful approximations to the other angles, but may not meet the default 0.99
threshold. A timeout means the search is incomplete, not that approximation is
impossible. These are full-unitary comparisons, not state-preparation checks.

### Custom angles

Use `--syn-axis rx|ry|rz` with `--syn-angle` to supply an angle in **radians**:

```bash
python run.py syn --syn-axis rx --syn-angle 'pi/4'
python run.py syn --syn-axis ry --syn-angle '2*pi/3' --syn-timeout 60
python run.py syn --syn-axis rz --syn-angle '0.42' --syn-fidelity 0.96
python run.py syn --syn-axis ry --syn-angle=-pi/4
```

Supported expressions contain numbers (including scientific notation), `pi`,
parentheses, and `+`, `-`, `*`, `/`. They are evaluated numerically with Python
floating-point precision; this is not symbolic-angle synthesis. Functions,
Python code, non-finite results, and division by zero are rejected. For negative
expressions use `--syn-angle=-pi/4`, avoiding command-line option ambiguity.
If only `--syn-angle` is supplied, the axis defaults to `rz`.
Do not combine custom-angle options with `--syn-target`.

The evaluated target is saved as `outputs/syn_custom/<axis>/target.qasm`, beside
its CNFs, solver logs, candidate QASM, and matrix-validation `result.json`.
Each axis has one reusable custom-output folder: changing its angle replaces
that axis's previous custom run. Named examples and the original Rz(pi/7)
outputs are retained separately. The requested expression is recorded in the
result's target label and its numeric value in `angle_radians`.

## One-qubit compositions with 2–5 gates

Eight commented QASM files in `circuits/` provide two nested progressions. Gates
below are in **execution order**; the matrix product is reversed. Each longer
target extends the preceding target by one gate.

| Gates | Exact control | Mixed-angle target |
|---|---|---|
| 2 | `ct2`: H, T | `mix2`: Rx(pi/4), Ry(pi/3) |
| 3 | `ct3`: H, T, H | `mix3`: Rx(pi/4), Ry(pi/3), Rz(pi/7) |
| 4 | `ct4`: H, T, H, T | `mix4`: Rx(pi/4), Ry(pi/3), Rz(pi/7), H |
| 5 | `ct5`: H, T, H, T, H | `mix5`: Rx(pi/4), Ry(pi/3), Rz(pi/7), H, T |

```bash
# First see exact synthesis at increasing target lengths.
python run.py syn --syn-target ct2
python run.py syn --syn-target ct3
python run.py syn --syn-target ct4
python run.py syn --syn-target ct5

# Then explore approximation of complete mixed-axis circuits.
python run.py syn --syn-target mix2
python run.py syn --syn-target mix3
python run.py syn --syn-target mix4
python run.py syn --syn-target mix5
```

Existing `--syn-fidelity` and `--syn-timeout` options also apply. Default settings
are fidelity 0.99 and the configured timeout (currently 200 seconds locally).
The exact controls are already expressible in the synthesis library and provide
known successful reference cases; they are not circuit-optimization benchmarks.

For mixed targets, the number of input gates does not predict synthesis depth or
search time. Noncommuting rotations combine into a new one-qubit unitary; the
solver approximates that entire unitary, not each rotation separately. Even a
two-gate input may require a long Clifford+T approximation. More input gates do
not necessarily mean greater difficulty, since compositions can simplify.

The matrix validator now computes the target and candidate matrices gate by gate
and compares `|Tr(U† C)|²/4`; it no longer assumes the target is one rotation.
The target matrix is computed before taking its inverse for synthesis. Reports
include `target_gates`; `axis` and `angle_radians` are null for compositions.
Each target retains a fixed folder under `outputs/syn_cases/<target>/`, replaced
on rerun. Individual QASM files remain editable in `circuits/`; supported matrix
validation gates are H, S/Sdg, T/Tdg, identity, and Rx/Ry/Rz on qubit zero.

## Multi-qubit targets without multi-qubit gates

Two commented QASM targets compare a joint Quokka# search with explicitly
splitting the target into independent one-qubit searches. Both methods allow
only H, S/Sdg, T/Tdg (and identity padding); no CX, CZ, or CCX choices are enabled.
The full Pauli cyclic score is used throughout, normalized by 4^n.

| Target | q0, in execution order | q1 | q2 | Suggested global threshold |
|---|---|---|---|---|
| `independent_rot2` | Rx(pi/3) | Ry(pi/3) | — | 0.96 |
| `independent_rot3` | Rx(pi/3) | Ry(pi/3) | Rz(pi/3) | 0.94 |

From `experiments/` with the existing virtual environment active:

```bash
python run.py syn --syn-target independent_rot2 --syn-fidelity 0.96 --syn-timeout 10
python run.py syn --syn-target independent_rot3 --syn-fidelity 0.94 --syn-timeout 10

# Select one method; the default for these four cases is compare.
python run.py syn --syn-target independent_rot2 --syn-mode separate --syn-fidelity 0.96
python run.py syn --syn-target independent_rot2 --syn-mode joint --syn-fidelity 0.96

# Harder global accuracy requirement; a timeout is an incomplete search.
python run.py syn --syn-target independent_rot2 --syn-fidelity 0.99 --syn-timeout 30
```

`compare` runs joint synthesis followed by separate synthesis. Each method gets
the stated total synthesis budget. Separate synthesis runs sequentially and
shares its budget across qubits, rather than granting that budget to every qubit.
Remaining time is rounded down to whole seconds for Quokka#'s alarm API; a wire
is skipped if less than one second remains. Parsing, validation, and reporting
add overhead, so this is not a hard end-to-end wall limit. An incomplete run
retains available candidates and explicitly reports whether a complete composed
candidate meets the global threshold. The combined candidate is never assumed
successful merely because local candidates exist.

### Why splitting works, and how fidelity changes

If every gate acts on one qubit, gates on different wires commute and the whole
unitary is `U = U0 tensor U1 tensor ...`. This is a property of the operation,
valid even when it is applied to an entangled input. It does not imply that an
arbitrary input state itself factors. Absence of CX/CCX alone is insufficient:
other multi-qubit operations also need consideration. The new runner rejects
multi-qubit gates instead of silently splitting them.

For product target and candidate circuits, trace multiplicativity gives

```
F(U, C) = |Tr(U† C)|² / 4^n = product_i F(Ui, Ci).
```

Thus local fidelity 0.99 on two wires guarantees only 0.9801 globally. The
separate method uses the sufficient equal allocation `local_threshold = tau^(1/n)`.
This allocation need not minimize total runtime, gate count, or parallel depth;
an uneven allocation can be better. The joint method applies only the global
threshold and can distribute approximation error unevenly. At a fixed common
depth with independent local gate choices and identity padding, the maximum
product fidelity is the product of the local maxima, since all factors are
nonnegative. Threshold-based early exits need not return those maxima.

With k choices per wire per layer and depth d, the naive joint sequence space
has k^(n*d) elements, versus n searches over k^d elements when split explicitly.
This is a search-space comparison, not a runtime theorem for MaxT: symbolic
decomposition, caching, pruning, and early stopping can already exploit structure.
Increasing n at fixed global fidelity also tightens the local fidelity budgets.

### Validation and output files

Every returned candidate is checked by explicit small dense matrices, independently
of the CNF solver. The global fidelity is also compared with the product of the
local matrix fidelities. Matrix construction uses q0 as the leftmost tensor
factor consistently for target and candidate. Dense validation is limited to
at most six qubits; the new examples use two or three.

Implementation: `product_synthesis.py` orchestrates the comparison and reuses
`synthesis_example.py`. Outputs are under `outputs/syn_cases/<target>/`, replaced
on rerun of that target, including when changing mode or threshold:

- `target.qasm`: the input used for this run.
- `comparison.json`: both method results, measured wall times, and configuration.
- `joint/`: original multi-qubit search, iteration log, CNFs, solver logs,
  candidate QASM, and `result.json`.
- `separate/`: combined candidate/report/log, plus `q0/`, `q1/`, etc. containing
  the remapped local target, search artifacts, and validation report.

Existing one-qubit commands and their output folders remain supported.

## Controlled comparison at a fixed synthesis depth

`fixed_depth_synthesis.py` compares joint synthesis against sequential per-qubit
synthesis at exactly the same template depth. It builds the target inverse,
adds exactly d local-gate choice layers, adds full Pauli cyclic boundaries,
and invokes MaxT once per resulting formula. It omits `--threshold`, disabling
threshold-based early success in the local MaxT build. Completed runs optimize
the fixed template instead of stopping at the first acceptable candidate or
iterating through smaller depths. Identity choices allow shorter circuits to
be represented inside the depth-d template.

```bash
python fixed_depth_synthesis.py --target independent_rot2 --depths 2 4 6 7 --repeats 3 --timeout 15
python fixed_depth_synthesis.py --target independent_rot3 --depths 2 4 6 7 --repeats 3 --timeout 15
```

Both methods use H, S/Sdg, T/Tdg and identity, with no multi-qubit gate choices.
Each method receives its own 15-second budget per repetition; separate synthesis
shares that budget across its local searches. Method order alternates across
repetitions. The methods run sequentially, avoiding competition for CPU during
timing. The reported solver times include process startup and waiting, exclude
CNF construction and matrix validation, and are summed across local calls for
the separate method. Encoding/setup and end-to-end times are recorded separately.

Every completed candidate is validated against its target matrix. For separate
synthesis, the global optimum fidelity is the product of the local optimum
fidelities; the runner asserts agreement with the completed joint result.
Timed-out or invalid runs are excluded from the complete-result median table
and are explicitly identified, rather than being treated as measured optima.

Outputs are under `outputs/fixed_depth/<target>/`, replaced on rerun of that
target. `results.json` records all timings and validation results, and
`d<depth>/repeat<index>/<method>/` contains CNFs, full solver logs, candidate
QASM, and individual reports. The earlier threshold-search outputs are separate.

This comparison uses MaxT's existing component decomposition; it is not a
brute-force enumerator. Literal brute force would consider up to 6^(n*d) raw
gate strings jointly versus n*6^d across independent local searches, ignoring
pruning and equivalent gate strings. That raw Cartesian-product comparison
does not describe the work performed by a solver that decomposes the formula.

### Larger independent-wire targets

Generate reproducible targets with more qubits and more gates per wire:

```bash
python fixed_depth_synthesis.py --qubits 4 --gates-per-qubit 6 --depths 4 6 --repeats 3 --timeout 20
python fixed_depth_synthesis.py --qubits 8 --gates-per-qubit 6 --depths 4 6 --repeats 3 --timeout 30
python fixed_depth_synthesis.py --qubits 16 --gates-per-qubit 6 --depths 4 6 --repeats 1 --timeout 60
python fixed_depth_synthesis.py --qubits 32 --gates-per-qubit 6 --depths 4 6 --repeats 1 --timeout 90
python fixed_depth_synthesis.py --qubits 8 --gates-per-qubit 12 --depths 4 6 7 --repeats 1 --timeout 30
```

Each wire alternates Rx, Ry, Rz with angles uniformly sampled from [-pi, pi]
using Python's `random.Random(seed + wire)`. The default seed is 20261022.
Larger qubit counts preserve the earlier wires; longer gate sequences preserve
each wire's earlier gate prefix. These are generated product unitaries, not
general entangling quantum circuits or Haar-random unitaries.

Commented inputs are saved in
`circuits/local_random_n<N>_g<G>_s<seed>.qasm` and copied into the corresponding
`outputs/fixed_depth/` directory. Rerunning the same generated target replaces
its previous results, including when changing the depths or repetitions.

Validation now computes the product of independent 2x2 matrix overlaps, which
requires only linear storage/work in the number of wires after their matrices
are built. Targets and candidates containing multi-qubit gates are rejected.
For up to six qubits, validation additionally checks against the full dense
matrix overlap. For larger n it never constructs a 2^n-by-2^n matrix. Solver
scores and joint/separate results are compared using relative tolerance 1e-8
and absolute tolerance 1e-14. Completed solver reports additionally retain
decision-node and max-component-split counters from the MaxT logs.

Input gate count and candidate template depth are distinct experimental axes.
Increasing the number of local input gates increases encoding size, but need
not monotonically increase synthesis difficulty: every wire still represents
one composed single-qubit unitary. The global optimum fidelity may decrease
as independent wires are added because their local fidelities multiply.

To retry incomplete runs with a larger budget while preserving completed,
validated results, repeat the original target/depth/repetition settings and
add `--resume`:

```bash
python fixed_depth_synthesis.py --qubits 8 --gates-per-qubit 12 --depths 4 6 7 --repeats 1 --timeout 300 --resume
```

Only incomplete or invalid method runs are replaced. Resume checks that target
generation, depths, and repetition count match the saved configuration.

Saved measurements are available under `outputs/fixed_depth/`; the consolidated
scaling table is `outputs/fixed_depth/scaling_summary.json`.

## Unequal per-qubit synthesis depths

`unequal_depth_synthesis.py` compares increasing-depth searches with independent
stopping. The cases use gate sequences in execution order:

| Target | q0 | q1 |
|---|---|---|
| `unequal_2_4` | HT | HTHT |
| `unequal_2_6` | HT | HTHTHT |
| `unequal_2_9` | HT | HTHTHTHTH |

Input gate counts label the fixtures; synthesis may find shorter equivalent
circuits. Each case runs joint synthesis, separate sequential synthesis, and
separate synthesis in two concurrent Python processes. Each process uses its
own output directory and MaxT instances. Each method runs once per case, in order: joint, sequential, then parallel.

Run from `experiments/` using the existing virtual environment. From the
repository root, first run `cd experiments`. Activation is optional when using
`.venv/bin/python` directly:

```sh
# Full suite: all three cases, each method once, with the configured timeout.
.venv/bin/python unequal_depth_synthesis.py

# Run a single depth comparison.
.venv/bin/python unequal_depth_synthesis.py --cases unequal_2_4
.venv/bin/python unequal_depth_synthesis.py --cases unequal_2_6
.venv/bin/python unequal_depth_synthesis.py --cases unequal_2_9

# Optional: give the depth-9 comparison a larger budget.
.venv/bin/python unequal_depth_synthesis.py --cases unequal_2_9 --timeout 300

# Optional: request near-exact fidelity.
.venv/bin/python unequal_depth_synthesis.py --cases unequal_2_9 --fidelity 0.999999
```

Every command runs all three methods: joint, separate sequential, and separate
parallel. `--timeout` is the budget in seconds **per method per case**,
not for the whole command. `--cases` accepts one or more names from the table;
omitting it selects all three cases. The default budget is taken from config `TIMEOUT` (currently 200 seconds in `config.local.json`).
A larger budget does not guarantee completion.

The default global process-fidelity threshold is 0.99. Independent searches
use its square root as their per-qubit threshold, then validate the composed
candidate against the global target. This is an approximate numerical criterion,
not a symbolic proof of equivalence. Use `--fidelity 0.999999` for near-exact searches. Joint synthesis can allocate error unevenly;
the independent searches use a sufficient equal allocation.

Reported elapsed time includes worker startup, encoding, synthesis and validation.
Separate sequential searches share the method's time budget; concurrent searches
receive the remaining budget when launched. Integer solver timeouts and process
startup can introduce small deviations from the requested wall-time budget.
Parallel synthesis uses two processes, so elapsed-time speedup is not a measure
of reduced CPU work. Reports retain per-qubit stopping depths, solver calls,
completed iteration times, final template-slot counts and independent fidelity
checks. A timeout remains an incomplete observation.

Artifacts are saved under `outputs/unequal_depth/<target>/`, including a copy of
the target, per-method logs and candidates, and `results.json`. Rerunning a
selected case replaces that case's artifacts, including when changing fidelity
or timeout. This runner has no `--resume` option: rerunning a case restarts all
three methods. Other cases are preserved. Each method writes to
`outputs/unequal_depth/<target>/<method>/`. Read the case's `results.json` for
individual elapsed times, stopping depths, and validation status. There is no
repetition loop or median aggregation.

The rotation product fixtures use `independent_rot2` and `independent_rot3`.
The redundant two- and three-qubit Clifford+T product fixtures were removed;
use the unequal-depth suite for those comparisons.
Historical output folders retain their original names to preserve provenance.

### Shared timeout configuration

All experiment runners use `TIMEOUT` from the selected Quokka configuration when
no command-line timeout is supplied. The default file is `config.local.json`;
`QUOKKA_CONFIG` selects another file. `run.py` and `benchmark.py` also accept
`--config`. Use `--syn-timeout` with `run.py`, or `--timeout` with the other
runners, to override the configured value for one invocation. The benchmark
wall-clock limit defaults to twice the resolved solver timeout and can be
overridden separately with `--wall-timeout`.
