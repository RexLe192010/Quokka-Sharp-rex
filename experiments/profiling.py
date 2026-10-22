"""Scoped instrumentation of the real Quokka# implementation (no algorithm copy)."""
from contextlib import contextmanager, ExitStack
from functools import wraps
import importlib
import json
from pathlib import Path
import subprocess
import threading
import time
from unittest.mock import patch

import psutil

MIB = 1024 ** 2


class Profiler:
    """Record nested wall times and sampled RSS; keep Python and solver RSS separate."""

    def __init__(self, interval=0.005):
        self.interval = interval
        self.events = []
        self.stack = []
        self.solvers = {}
        self.processes = []
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.process = psutil.Process()

    def sample(self):
        with self.lock:
            try:
                rss = self.process.memory_info().rss / MIB
                if self.stack:
                    row = self.stack[-1]
                    row['python_peak_rss_mib'] = max(row['python_peak_rss_mib'], rss)
            except psutil.Error:
                pass
            for pid, row in list(self.solvers.items()):
                try:
                    proc = psutil.Process(pid)
                    # Sum simultaneous RSS across this solver's process tree.
                    rss = proc.memory_info().rss
                    for child in proc.children(recursive=True):
                        try:
                            rss += child.memory_info().rss
                        except psutil.Error:
                            pass
                    row['solver_peak_rss_mib'] = max(row['solver_peak_rss_mib'] or 0, rss / MIB)
                    row['rss_samples'] += 1
                except psutil.Error:
                    pass

    def sample_loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    @contextmanager
    def span(self, phase):
        row = dict(phase=phase, wall_s=0, exclusive_s=0,
                   python_peak_rss_mib=0, solver_peak_rss_mib=None,
                   children_s=0)
        with self.lock:
            self.stack.append(row)
        self.sample()
        start = time.perf_counter()
        try:
            yield row
        finally:
            self.sample()
            elapsed = time.perf_counter() - start
            with self.lock:
                self.stack.pop()
                row['wall_s'] = elapsed
                row['exclusive_s'] = max(0, elapsed - row.pop('children_s'))
                if self.stack:
                    self.stack[-1]['children_s'] += elapsed
                self.events.append(row)

    def wrap(self, function, phase, cnf_output=False):
        @wraps(function)
        def measured(*args, **kwargs):
            with self.span(phase) as row:
                result = function(*args, **kwargs)
                if cnf_output:
                    cnf = args[0]
                    path = Path(args[1] if len(args) > 1 else kwargs['cnf_file'])
                    row.update(cnf_file=str(path), variables=cnf.vars.var,
                               clauses=cnf.clause, file_bytes=path.stat().st_size,
                               depth=cnf.syn_gate_layer)
                return result
        return measured

    def popen_class(self, phase):
        profiler = self

        class MeasuredPopen(subprocess.Popen):
            def __init__(self, command, *args, **kwargs):
                self.profile_started = time.perf_counter()
                self.profile_finished = False
                self.profile_owner = profiler.stack[-1] if profiler.stack else None
                super().__init__(command, *args, **kwargs)
                self.profile_row = dict(phase=phase, command=list(command),
                                        python_peak_rss_mib=None,
                                        solver_peak_rss_mib=None, rss_samples=0)
                with profiler.lock:
                    profiler.solvers[self.pid] = self.profile_row
                    profiler.processes.append(self)
                profiler.sample()

            def communicate(self, *args, **kwargs):
                result = super().communicate(*args, **kwargs)
                self.finish_profile()
                return result

            def finish_profile(self):
                if self.profile_finished:
                    return
                self.profile_finished = True
                elapsed = time.perf_counter() - self.profile_started
                with profiler.lock:
                    profiler.solvers.pop(self.pid, None)
                    self.profile_row.update(wall_s=elapsed, exclusive_s=elapsed,
                                            returncode=self.returncode)
                    profiler.events.append(self.profile_row)
                    if self.profile_owner is not None and 'children_s' in self.profile_owner:
                        self.profile_owner['children_s'] += elapsed
        return MeasuredPopen

    @contextmanager
    def instrument(self):
        """Temporarily wrap methods used by CheckEquivalence/Synthesis, then restore."""
        eq = importlib.import_module('quokka_sharp.eq')
        syn = importlib.import_module('quokka_sharp.syn')
        from quokka_sharp.encoding.cnf import CNF
        thread = threading.Thread(target=self.sample_loop, daemon=True)
        thread.start()
        try:
            with ExitStack() as patches:
                for owner, name, phase in [
                    (eq, 'basis', 'query_constraints'),
                    (eq, 'identity_check', 'query_constraints'),
                    (syn, 'identity_check', 'query_constraints'),
                    (CNF, 'add_syn_layer', 'template_encoding'),
                    (CNF, 'get_syn_qasm', 'decode_qasm'),
                    (eq, 'get_result', 'parse_solver_result'),
                    (syn, 'get_result', 'parse_solver_result'),
                ]:
                    patches.enter_context(patch.object(owner, name, self.wrap(getattr(owner, name), phase)))
                patches.enter_context(patch.object(CNF, 'write_to_file', self.wrap(CNF.write_to_file, 'cnf_write', True)))
                patches.enter_context(patch.object(eq, 'Popen', self.popen_class('wmc_solver')))
                patches.enter_context(patch.object(syn, 'Popen', self.popen_class('maxT')))
                yield self
        finally:
            # In particular, upstream synthesis kills but does not always reap
            # its subprocess on timeout. Do not leave a solver running.
            for proc in self.processes:
                if not proc.profile_finished:
                    try:
                        if proc.poll() is None:
                            for child in psutil.Process(proc.pid).children(recursive=True):
                                child.kill()
                            proc.kill()
                        proc.communicate(timeout=2)
                    except (psutil.Error, subprocess.TimeoutExpired):
                        proc.finish_profile()
            self.stop.set()
            thread.join(timeout=1)

    def save(self, directory):
        import csv
        directory = Path(directory)
        (directory / 'profile.json').write_text(json.dumps(self.events, indent=2))
        phases = {}
        for row in self.events:
            phase = phases.setdefault(row['phase'], dict(phase=row['phase'], calls=0,
                exclusive_s=0, inclusive_s=0, python_peak_rss_mib=None, solver_peak_rss_mib=None))
            phase['calls'] += 1
            phase['exclusive_s'] += row['exclusive_s']
            phase['inclusive_s'] += row['wall_s']
            for key in ['python_peak_rss_mib', 'solver_peak_rss_mib']:
                if row[key] is not None:
                    phase[key] = max(phase[key] or 0, row[key])
        with (directory / 'phases.csv').open('w') as handle:
            columns = ['phase', 'calls', 'exclusive_s', 'inclusive_s', 'python_peak_rss_mib', 'solver_peak_rss_mib']
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(phases.values())
        return phases
