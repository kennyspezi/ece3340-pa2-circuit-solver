"""
schematic.py -- the circuit model behind the GUI (no graphics here).

    Schematic  : parts and wires on a grid, saved/loaded as JSON
    nets()     : which grid points are electrically connected
    netlist()  : Schematic -> netlist text (the format solver reads)
    run_solver : write netlist, call the C++ solver, parse its output

ECE 3340 -- students do not need to change this file.
"""
import json
import os
import re
import subprocess
import tempfile

# ----------------------------------------------------------------------
# Parts
# ----------------------------------------------------------------------
# kind: two terminals: 'R', 'C', 'L', 'V', 'I'
#       four terminals: 'E' (VCVS), 'G' (VCCS)
#       one terminal:   'GND'
# (x, y): grid position of terminal 1.
# Two-terminal parts span 2 grid units; rot: 0 right, 1 down, 2 left, 3 up is the
# direction from terminal 1 (n+) to terminal 2 (n-).
# Four-terminal parts occupy a 2 x 2 square: control + / - on the left
# (x, y) and (x, y+2); output + / - on the right (x+2, y) and (x+2, y+2).
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]
PART_LEN = 2
TWO_TERMINAL = ('R', 'C', 'L', 'V', 'I')
FOUR_TERMINAL = ('E', 'G')
SOURCES = ('V', 'I')
PREFIX = {'R': 'R', 'C': 'C', 'L': 'L', 'V': 'V', 'I': 'I', 'E': 'E', 'G': 'G'}
DEFAULT_VALUE = {'R': '1k', 'C': '1u', 'L': '1m', 'V': '5', 'I': '1m', 'E': '10', 'G': '10m'}
UNITS = {'R': 'Ω', 'C': 'F', 'L': 'H', 'V': 'V', 'I': 'A', 'E': 'V/V', 'G': 'S'}
NAMES = {'R': 'resistor', 'C': 'capacitor', 'L': 'inductor', 'V': 'voltage source',
         'I': 'current source', 'E': 'VCVS', 'G': 'VCCS', 'GND': 'ground'}

_SUFFIX = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3,
           'k': 1e3, 'g': 1e9, 't': 1e12}


def parse_value(text):
    """Same rules as the C++ solver: '4.7k' -> 4700.0, '1meg' -> 1e6.
    Returns None if text does not start with a number."""
    m = re.match(r'\s*([-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?)(\S*)\s*$', text)
    if not m:
        return None
    v = float(m.group(1))
    suf = m.group(4).lower()
    if suf.startswith('meg'):
        return v * 1e6
    if suf and suf[0] in _SUFFIX:
        return v * _SUFFIX[suf[0]]
    return v


def parse_source(text):
    """A source value: '5', 'DC 5', 'PULSE(v1 v2 [td tr tf pw per])', 'SIN(vo va f [td])'.
    Returns (kind, [numbers]) or None. Mirrors the C++ solver."""
    t = text.strip()
    m = re.match(r'(?i)^(pulse|sin)\s*\((.*)\)\s*$', t)
    if m:
        nums = [parse_value(x) for x in re.split(r'[\s,]+', m.group(2).strip()) if x]
        if None in nums:
            return None
        kind = m.group(1).upper()
        if (kind == 'PULSE' and 2 <= len(nums) <= 7) or (kind == 'SIN' and 3 <= len(nums) <= 4):
            return kind, nums
        return None
    t = re.sub(r'(?i)^dc\s+', '', t)
    v = parse_value(t)
    return ('DC', [v]) if v is not None else None


def eng(v, unit=''):
    """Format a number with an SI prefix: 0.0025 -> '2.5 m'."""
    if abs(v) < 1e-13:          # round-off noise around zero
        v = 0.0
    if v == 0 or not (abs(v) < 1e300):
        return f'{v:g} {unit}'.strip()
    for scale, pre in ((1e12, 'T'), (1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1, ''),
                       (1e-3, 'm'), (1e-6, 'µ'), (1e-9, 'n'), (1e-12, 'p')):
        if abs(v) >= scale * 0.9995:
            return f'{v / scale:.4g} {pre}{unit}'.strip()
    return f'{v:.3g} {unit}'.strip()


class Part:
    def __init__(self, kind, x, y, rot=0, name='', value=''):
        self.kind, self.x, self.y, self.rot = kind, x, y, rot
        self.name = name
        self.value = value or DEFAULT_VALUE.get(kind, '')

    def terminals(self):
        """Grid points of the terminals, in netlist order."""
        if self.kind == 'GND':
            return [(self.x, self.y)]
        if self.kind in FOUR_TERMINAL:      # out+, out-, ctl+, ctl-  (netlist order)
            x, y = self.x, self.y
            return [(x + 2, y), (x + 2, y + 2), (x, y), (x, y + 2)]
        dx, dy = DIRS[self.rot]
        return [(self.x, self.y), (self.x + PART_LEN * dx, self.y + PART_LEN * dy)]

    def to_dict(self):
        return dict(kind=self.kind, x=self.x, y=self.y, rot=self.rot,
                    name=self.name, value=self.value)

    @staticmethod
    def from_dict(d):
        return Part(d['kind'], d['x'], d['y'], d.get('rot', 0), d.get('name', ''), d.get('value', ''))


class Wire:
    """A horizontal or vertical segment between two grid points."""
    def __init__(self, a, b):
        self.a, self.b = tuple(a), tuple(b)

    def contains(self, p):
        (x1, y1), (x2, y2), (x, y) = self.a, self.b, p
        if x1 == x2 == x:
            return min(y1, y2) <= y <= max(y1, y2)
        if y1 == y2 == y:
            return min(x1, x2) <= x <= max(x1, x2)
        return False

    def to_dict(self):
        return dict(a=list(self.a), b=list(self.b))


# ----------------------------------------------------------------------
# Schematic
# ----------------------------------------------------------------------
class Schematic:
    def __init__(self):
        self.parts = []
        self.wires = []
        # 'dc', or 'tran' with a time step and stop time (SPICE value strings)
        self.analysis = {'type': 'dc', 'step': '10u', 'stop': '5m'}

    # --- editing -------------------------------------------------------
    def next_name(self, kind):
        used = {p.name.upper() for p in self.parts}
        k = 1
        while f'{PREFIX[kind]}{k}'.upper() in used:
            k += 1
        return f'{PREFIX[kind]}{k}'

    def add_part(self, kind, x, y, rot=0):
        name = '' if kind == 'GND' else self.next_name(kind)
        p = Part(kind, x, y, rot if kind in TWO_TERMINAL else 0, name)
        self.parts.append(p)
        return p

    def add_wire(self, a, b):
        """Add an L-shaped connection from a to b (one or two straight segments)."""
        a, b = tuple(a), tuple(b)
        if a == b:
            return []
        if a[0] == b[0] or a[1] == b[1]:
            segs = [Wire(a, b)]
        else:
            corner = (b[0], a[1])
            segs = [Wire(a, corner), Wire(corner, b)]
        self.wires.extend(segs)
        return segs

    def remove(self, obj):
        if obj in self.parts:
            self.parts.remove(obj)
        elif obj in self.wires:
            self.wires.remove(obj)

    # --- connectivity --------------------------------------------------
    def nets(self):
        """Group connected grid points.

        Two points are connected if a wire runs between them (a terminal or wire
        end that lands anywhere on a wire, not just its ends, is connected --
        a T-junction). Wires that merely cross are NOT connected.

        Returns (net_of, names):
          net_of[point] -> net id for every terminal/wire-end point
          names[net id] -> '0' for ground, otherwise 'n1', 'n2', ... in a
                           stable order (top-to-bottom, then left-to-right)
        """
        parent = {}

        def find(p):
            parent.setdefault(p, p)
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        def union(p, q):
            parent[find(p)] = find(q)

        points = set()
        for part in self.parts:
            points.update(part.terminals())
        for w in self.wires:
            points.update((w.a, w.b))
        for p in points:
            find(p)
        for w in self.wires:
            for p in points:
                if w.contains(p):
                    union(p, w.a)

        groups = {}
        for p in points:
            groups.setdefault(find(p), []).append(p)

        ground_roots = {find(part.terminals()[0]) for part in self.parts if part.kind == 'GND'}
        names, net_of = {}, {}
        k = 1
        for root in sorted(groups, key=lambda r: min((q[1], q[0]) for q in groups[r])):
            if root in ground_roots:
                names[root] = '0'
            else:
                names[root] = f'n{k}'
                k += 1
            for p in groups[root]:
                net_of[p] = root
        return net_of, names

    def node_name(self, point):
        net_of, names = self.nets()
        return names.get(net_of.get(tuple(point)))

    # --- netlist ------------------------------------------------------
    def check(self):
        """Return a list of problems that would stop the solver."""
        errs = []
        if not any(p.kind == 'GND' for p in self.parts):
            errs.append('No ground. Place a ground symbol (G).')
        if not any(p.kind != 'GND' for p in self.parts):
            errs.append('No components.')
        for p in self.parts:
            if p.kind == 'GND':
                continue
            if p.kind in SOURCES:
                if parse_source(p.value) is None:
                    errs.append(f'{p.name}: "{p.value}" is not a number, PULSE(...) or SIN(...).')
                continue
            v = parse_value(p.value)
            if v is None:
                errs.append(f'{p.name}: value "{p.value}" is not a number.')
            elif p.kind in ('R', 'C', 'L') and v <= 0:
                errs.append(f'{p.name}: value must be > 0.')
        net_of, names = self.nets()
        for p in self.parts:
            if p.kind != 'GND':
                ts = p.terminals()
                a, b = names[net_of[ts[0]]], names[net_of[ts[1]]]
                if a == b:
                    errs.append(f'{p.name} is shorted (both ends on node {a}).')
        if self.analysis.get('type') == 'tran':
            h, T = parse_value(self.analysis.get('step', '')), parse_value(self.analysis.get('stop', ''))
            if h is None or T is None or not (0 < h < T):
                errs.append('Transient settings: need 0 < step < stop.')
            elif T / h > 1e6:
                errs.append('Transient settings: more than a million steps; use a larger step.')
        return errs

    def netlist(self, title='circuit drawn in circuit_gui'):
        net_of, names = self.nets()
        lines = [f'* {title}']
        for kind in ('V', 'I', 'E', 'G', 'R', 'C', 'L'):
            for p in sorted((q for q in self.parts if q.kind == kind),
                            key=lambda q: (len(q.name), q.name)):
                nodes = ' '.join(names[net_of[t]] for t in p.terminals())
                lines.append(f'{p.name} {nodes} {p.value}')
        if self.analysis.get('type') == 'tran':
            lines.append(f".tran {self.analysis['step']} {self.analysis['stop']}")
        lines.append('.end')
        return '\n'.join(lines) + '\n'

    # --- files ----------------------------------------------------------
    def save(self, path):
        with open(path, 'w') as f:
            json.dump(dict(parts=[p.to_dict() for p in self.parts],
                           wires=[w.to_dict() for w in self.wires],
                           analysis=self.analysis), f, indent=1)

    @staticmethod
    def load(path):
        with open(path) as f:
            d = json.load(f)
        s = Schematic()
        s.parts = [Part.from_dict(p) for p in d.get('parts', [])]
        s.wires = [Wire(w['a'], w['b']) for w in d.get('wires', [])]
        s.analysis.update(d.get('analysis', {}))
        return s


# ----------------------------------------------------------------------
# Running the solver
# ----------------------------------------------------------------------
_RESULT = re.compile(r'^\s*([VI])\((.+)\)\s*=\s*(\S+)\s*$')


def parse_solver_output(text):
    """Parse what solver prints.

    DC:        'V(n1) = 5' lines.
    Transient: a header 'time V(n1) ... I(V1)' then one row of numbers per step.

    Returns (volts, amps, tran): volts {node: V} and amps {source: A} at the
    end time; tran = None for DC, else dict(cols=[...], rows=[[t, ...], ...]).
    """
    volts, amps, tran = {}, {}, None
    for line in text.splitlines():
        if line.startswith('time '):
            tran = dict(cols=line.split()[1:], rows=[])
            continue
        if tran is not None and line and line[0] not in '#':
            try:
                tran['rows'].append([float(x) for x in line.split()])
            except ValueError:
                pass
            continue
        m = _RESULT.match(line)
        if m:
            (volts if m.group(1) == 'V' else amps)[m.group(2)] = float(m.group(3))
    if tran and tran['rows']:
        last = tran['rows'][-1]
        for name, v in zip(tran['cols'], last[1:]):
            m = re.match(r'([VI])\((.+)\)$', name)
            if m:
                (volts if m.group(1) == 'V' else amps)[m.group(2)] = v
    return volts, amps, tran


def default_solver_path():
    """Look for the solver built in ../solver next to this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ('solver.exe', 'solver'):
        p = os.path.normpath(os.path.join(here, '..', 'solver', name))
        if os.path.isfile(p):
            return p
    return ''


def run_solver(solver_path, netlist_text, options=(), timeout=60):
    """Write the netlist to a temp file and run the solver on it.

    Returns dict(ok, volts, amps, tran, stdout, stderr, netlist_file).
    """
    fd, path = tempfile.mkstemp(suffix='.cir', prefix='circuit_')
    with os.fdopen(fd, 'w') as f:
        f.write(netlist_text)
    try:
        r = subprocess.run([solver_path, *options, path], capture_output=True,
                           text=True, timeout=timeout)
    except FileNotFoundError:
        return dict(ok=False, volts={}, amps={}, tran=None, stdout='',
                    stderr=f'Solver not found: {solver_path}\nBuild it with "make" in the solver folder,\n'
                           'then choose it with Solver > Choose solver program.',
                    netlist_file=path)
    except subprocess.TimeoutExpired:
        return dict(ok=False, volts={}, amps={}, tran=None, stdout='',
                    stderr=f'Solver did not finish within {timeout} s (infinite loop?).',
                    netlist_file=path)
    volts, amps, tran = parse_solver_output(r.stdout)
    return dict(ok=(r.returncode == 0), volts=volts, amps=amps, tran=tran,
                stdout=r.stdout, stderr=r.stderr, netlist_file=path)
