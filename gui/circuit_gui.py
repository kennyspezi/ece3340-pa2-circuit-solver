"""
circuit_gui.py -- draw a circuit, solve it with YOUR C++ solver, see the results.

    python circuit_gui.py              (Python 3.8+, tkinter is built in)

How it works:
    1. You draw parts and wires on the grid.
    2. The GUI turns the drawing into a netlist (shown on the right).
    3. "Solve" (F5) runs the solver program you built in ../solver on that
       netlist. DC: node voltages appear on the drawing. Transient: a plot
       window shows the waveforms, and the drawing shows the final values.

Keys:   R resistor   C capacitor   L inductor   V voltage source   I current source
        E VCVS       G ground      W wire       Esc select/move    D delete
        Space rotate F5 solve      Double-click a part to change its value
        (VCCS: toolbar button)

ECE 3340 -- students do not need to change this file.
"""
import math
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from schematic import (Schematic, Part, DIRS, UNITS, NAMES, TWO_TERMINAL, FOUR_TERMINAL,
                       SOURCES, parse_value, parse_source, eng, default_solver_path, run_solver)

GRID = 32                      # pixels per grid unit
COLS, ROWS = 32, 20            # drawing area in grid units
COL_PART = '#1f2937'
COL_WIRE = '#2563eb'
COL_SEL = '#f59e0b'
COL_GHOST = '#9ca3af'
COL_GRID = '#d1d5db'
COL_RESULT = '#b91c1c'
COL_NODE = '#6b7280'
TRACE_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#4d7c0f', '#be185d']

PLACE_TOOLS = ('R', 'C', 'L', 'V', 'I', 'E', 'G', 'GND')
HINTS = {
    'select': 'Select: click a part or wire; drag to move; Space rotates; Delete removes; double-click edits value.',
    'wire':   'Wire: click a start point, then the end point. Keep clicking to continue; Esc or right-click stops.',
    'R':      'Resistor: click to place. Space rotates before placing.',
    'C':      'Capacitor: click to place. Open circuit in DC; C/h companion model in transient.',
    'L':      'Inductor: click to place. Short circuit in DC; L/h companion model in transient.',
    'V':      'Voltage source: V(+) − V(−) = value. Value: 5, PULSE(0 5 1m) or SIN(0 1 1k).',
    'I':      'Current source: arrow = current through the source. Value: 1m, PULSE(…) or SIN(…).',
    'E':      'VCVS: output (right) = gain × (control + minus control −, on the left).',
    'G':      'VCCS: output current (right, top → bottom through it) = gm × (control + minus control −).',
    'GND':    'Ground: click on a terminal or wire end. Every circuit needs one.',
    'delete': 'Delete: click a part or wire to remove it.',
}


class CircuitGUI:
    def __init__(self, root):
        self.root = root
        self.sch = Schematic()
        self.file = None
        self.solver = default_solver_path()
        self.tool = 'select'
        self.rot = 0                 # rotation for the part being placed
        self.mouse = (0, 0)          # mouse position in grid units
        self.wire_start = None
        self.last_click = None
        self.selected = None
        self.drag_from = None
        self.results = None          # (volts by node, amps by source) -- peaks for transient
        self.tran_labels = False     # True: the node labels show transient peaks
        self.tran = None             # last transient data, for the plot
        self.plot = None
        self.opt_matrix = tk.BooleanVar(value=False)
        self.analysis_var = tk.StringVar(value='dc')

        self._build_window()
        self._bind_keys()
        self.set_tool('select')
        self.refresh()

    # ------------------------------------------------------------------
    # Window layout
    # ------------------------------------------------------------------
    def _build_window(self):
        r = self.root
        r.title('ECE 3340 Circuit Solver')

        menu = tk.Menu(r)
        fm = tk.Menu(menu, tearoff=0)
        fm.add_command(label='New', command=self.new)
        fm.add_command(label='Open…', command=self.open)
        fm.add_command(label='Save', command=self.save)
        fm.add_command(label='Save as…', command=lambda: self.save(ask=True))
        fm.add_separator()
        fm.add_command(label='Export netlist (.cir)…', command=self.export_netlist)
        fm.add_separator()
        fm.add_command(label='Quit', command=r.destroy)
        menu.add_cascade(label='File', menu=fm)
        am = tk.Menu(menu, tearoff=0)
        am.add_radiobutton(label='DC operating point', value='dc', variable=self.analysis_var,
                           command=self.set_analysis)
        am.add_radiobutton(label='Transient', value='tran', variable=self.analysis_var,
                           command=self.set_analysis)
        am.add_separator()
        am.add_command(label='Transient step and stop time…', command=self.edit_tran)
        menu.add_cascade(label='Analysis', menu=am)
        sm = tk.Menu(menu, tearoff=0)
        sm.add_command(label='Solve  (F5)', command=self.solve)
        sm.add_command(label='Show waveform plot', command=self.show_plot)
        sm.add_checkbutton(label='Print matrix A and b (--matrix)', variable=self.opt_matrix)
        sm.add_separator()
        sm.add_command(label='Choose solver program…', command=self.choose_solver)
        menu.add_cascade(label='Solver', menu=sm)
        r.config(menu=menu)

        bar = ttk.Frame(r, padding=4)
        bar.pack(side='top', fill='x')
        for key, label in (('select', 'Select'), ('wire', 'Wire'), ('R', 'R'), ('C', 'C'), ('L', 'L'),
                           ('V', 'V src'), ('I', 'I src'), ('E', 'VCVS'), ('G', 'VCCS'),
                           ('GND', 'Ground'), ('delete', 'Delete')):
            ttk.Button(bar, text=label, width=len(label) + 1,
                       command=lambda k=key: self.set_tool(k)).pack(side='left', padx=1)
        ttk.Button(bar, text='▶ Solve', command=self.solve).pack(side='right', padx=2)
        self.analysis_btn = ttk.Button(bar, command=self.edit_tran)
        self.analysis_btn.pack(side='right', padx=4)

        self.status = tk.StringVar()
        ttk.Label(r, textvariable=self.status, anchor='w', padding=(6, 2)).pack(side='bottom', fill='x')

        body = ttk.PanedWindow(r, orient='horizontal')
        body.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(body, width=COLS * GRID, height=ROWS * GRID, bg='white',
                                highlightthickness=0)
        body.add(self.canvas, weight=3)

        side = ttk.Frame(body, padding=4)
        body.add(side, weight=1)
        ttk.Label(side, text='Netlist (what the solver reads)').pack(anchor='w')
        self.net_text = tk.Text(side, width=44, height=12, font=('Courier', 10), wrap='none')
        self.net_text.pack(fill='both', expand=False)
        ttk.Label(side, text='Results').pack(anchor='w', pady=(8, 0))
        self.out_text = tk.Text(side, width=44, height=20, font=('Courier', 10), wrap='none')
        self.out_text.pack(fill='both', expand=True)

    def _bind_keys(self):
        c, r = self.canvas, self.root
        c.bind('<Motion>', self.on_move)
        c.bind('<Button-1>', self.on_click)
        c.bind('<B1-Motion>', self.on_drag)
        c.bind('<ButtonRelease-1>', self.on_release)
        c.bind('<Double-Button-1>', self.on_double)
        c.bind('<Button-3>', lambda e: self.cancel())
        for key, tool in (('r', 'R'), ('c', 'C'), ('l', 'L'), ('v', 'V'), ('i', 'I'), ('e', 'E'),
                          ('g', 'GND'), ('w', 'wire'), ('d', 'delete')):
            r.bind(f'<Key-{key}>', lambda e, t=tool: self._key_tool(e, t))
        r.bind('<Escape>', lambda e: self.cancel())
        r.bind('<space>', lambda e: self._key_guard(e, self.rotate))
        r.bind('<Delete>', lambda e: self._key_guard(e, self.delete_selected))
        r.bind('<BackSpace>', lambda e: self._key_guard(e, self.delete_selected))
        r.bind('<F5>', lambda e: self.solve())

    def _typing(self, event):
        return isinstance(event.widget, tk.Text) or event.widget.winfo_toplevel() is not self.root

    def _key_tool(self, event, tool):
        if not self._typing(event):
            self.set_tool(tool)

    def _key_guard(self, event, fn):
        if not self._typing(event):
            fn()

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def set_tool(self, tool):
        if tool != self.tool:
            self.rot = 0             # each new part starts unrotated
        self.tool = tool
        self.wire_start = None
        if tool != 'select':
            self.selected = None
        self.status.set(HINTS[tool])
        self.redraw()

    def cancel(self):
        if self.tool == 'wire' and self.wire_start:
            self.wire_start = None
            self.redraw()
        else:
            self.set_tool('select')

    def rotate(self):
        if self.tool in TWO_TERMINAL:
            self.rot = (self.rot + 1) % 4
            self.redraw()
        elif isinstance(self.selected, Part) and self.selected.kind in TWO_TERMINAL:
            self.selected.rot = (self.selected.rot + 1) % 4
            self.changed()

    def delete_selected(self):
        if self.selected is not None:
            self.sch.remove(self.selected)
            self.selected = None
            self.changed()

    # ------------------------------------------------------------------
    # Analysis settings
    # ------------------------------------------------------------------
    def set_analysis(self):
        self.sch.analysis['type'] = self.analysis_var.get()
        self.changed()

    def edit_tran(self):
        a = self.sch.analysis
        step = simpledialog.askstring('Transient', 'Time step h (e.g. 10u):',
                                      initialvalue=a.get('step', '10u'), parent=self.root)
        if step is None:
            return
        stop = simpledialog.askstring('Transient', 'Stop time (e.g. 5m):',
                                      initialvalue=a.get('stop', '5m'), parent=self.root)
        if stop is None:
            return
        h, T = parse_value(step), parse_value(stop)
        if h is None or T is None or not (0 < h < T):
            messagebox.showerror('Transient', 'Need numbers with 0 < step < stop.')
            return
        a.update(type='tran', step=step.strip(), stop=stop.strip())
        self.analysis_var.set('tran')
        self.changed()

    def _analysis_text(self):
        a = self.sch.analysis
        if a.get('type') == 'tran':
            return f"Tran {a['step']} / {a['stop']}"
        return 'DC'

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------
    @staticmethod
    def to_grid(e):
        return (round(e.x / GRID), round(e.y / GRID))

    def on_move(self, e):
        g = self.to_grid(e)
        if g != self.mouse:
            self.mouse = g
            if self.tool != 'select':
                self.redraw()

    def on_click(self, e):
        g = self.to_grid(e)
        self.last_click = (g, self.tool)
        if self.tool in PLACE_TOOLS:
            self.sch.add_part(self.tool, g[0], g[1], self.rot)
            self.changed()
        elif self.tool == 'wire':
            if self.wire_start is None:
                self.wire_start = g
            elif g != self.wire_start:
                self.sch.add_wire(self.wire_start, g)
                self.wire_start = g          # keep drawing from here
                self.changed()
        elif self.tool == 'delete':
            obj = self.hit(e.x, e.y)
            if obj is not None:
                self.sch.remove(obj)
                self.changed()
        else:  # select
            self.selected = self.hit(e.x, e.y)
            self.drag_from = g if isinstance(self.selected, Part) else None
            self.redraw()

    def on_drag(self, e):
        if self.tool == 'select' and self.drag_from and isinstance(self.selected, Part):
            g = self.to_grid(e)
            dx, dy = g[0] - self.drag_from[0], g[1] - self.drag_from[1]
            if dx or dy:
                self.selected.x += dx
                self.selected.y += dy
                self.drag_from = g
                self.changed()

    def on_release(self, e):
        self.drag_from = None

    def on_double(self, e):
        """Tk reports two quick clicks as a double-click and skips the second
        <Button-1>. A real double-click is on the same point with the same tool;
        otherwise treat it as an ordinary click so fast drawing loses no clicks."""
        g = self.to_grid(e)
        if (g, self.tool) != self.last_click:
            self.on_click(e)
            return
        if self.tool == 'select':
            obj = self.hit(e.x, e.y)
            if isinstance(obj, Part) and obj.kind != 'GND':
                self.edit_value(obj)
        elif self.tool == 'wire':
            self.wire_start = None       # double-click ends the wire
            self.redraw()

    def edit_value(self, part):
        unit = UNITS[part.kind]
        if part.kind in SOURCES:
            prompt = (f'{part.name} value in {unit}:\n  a number (5, 2m)\n  PULSE(v1 v2 td tr tf pw per)'
                      f'\n  SIN(vo va freq td)')
        else:
            prompt = f'{part.name} value in {unit}\n(suffixes ok: 4.7k, 2m, 10u, 1meg)'
        while True:
            s = simpledialog.askstring('Value', prompt, initialvalue=part.value, parent=self.root)
            if s is None:
                return
            if part.kind in SOURCES:
                ok = parse_source(s) is not None
            else:
                v = parse_value(s)
                ok = v is not None and (v > 0 or part.kind in FOUR_TERMINAL)
            if ok:
                part.value = s.strip()
                self.changed()
                return
            messagebox.showerror('Value', f'"{s}" is not a valid value for a {NAMES[part.kind]}.')

    def hit(self, px, py):
        """Part or wire under pixel (px, py), or None."""
        best, best_d = None, 8.0
        for p in self.sch.parts:
            ts = p.terminals()
            if p.kind == 'GND':
                (x, y), = ts
                d = math.hypot(px - x * GRID, py - (y + 0.6) * GRID) - 0.5 * GRID
            elif p.kind in FOUR_TERMINAL:
                inside = (p.x - 0.3) * GRID <= px <= (p.x + 2.3) * GRID and \
                         (p.y - 0.3) * GRID <= py <= (p.y + 2.3) * GRID
                d = 0.0 if inside else 99.0
            else:
                d = _seg_dist(px, py, ts[0], ts[1]) - 0.35 * GRID
            if d < best_d:
                best, best_d = p, d
        for w in self.sch.wires:
            d = _seg_dist(px, py, w.a, w.b)
            if d < best_d:
                best, best_d = w, d
        return best

    # ------------------------------------------------------------------
    # Model changed -> update netlist panel and drawing
    # ------------------------------------------------------------------
    def changed(self):
        self.results = None          # old results no longer match the drawing
        self.refresh()

    def refresh(self):
        self.analysis_var.set(self.sch.analysis.get('type', 'dc'))
        self.analysis_btn.config(text=self._analysis_text())
        self.net_text.delete('1.0', 'end')
        self.net_text.insert('1.0', self.sch.netlist())
        self.redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def redraw(self):
        c = self.canvas
        c.delete('all')
        for gx in range(COLS + 1):
            for gy in range(ROWS + 1):
                x, y = gx * GRID, gy * GRID
                c.create_rectangle(x, y, x + 1, y + 1, outline=COL_GRID, fill=COL_GRID)

        net_of, names = self.sch.nets()

        for w in self.sch.wires:
            col = COL_SEL if w is self.selected else COL_WIRE
            c.create_line(*_px(w.a), *_px(w.b), fill=col, width=2)

        for p in self.sch.parts:
            draw_part(c, p, COL_SEL if p is self.selected else COL_PART)

        self._draw_dots()
        self._draw_node_labels(net_of, names)
        self._draw_ghost()

    def _draw_dots(self):
        """Filled dot where 3+ things meet; red ring on a terminal connected to nothing."""
        deg = {}
        for p in self.sch.parts:
            for t in p.terminals():
                deg[t] = deg.get(t, 0) + 1
        for w in self.sch.wires:
            for t in (w.a, w.b):
                deg[t] = deg.get(t, 0) + 1
        for w in self.sch.wires:
            for t in list(deg):
                if t not in (w.a, w.b) and w.contains(t):
                    deg[t] += 2
        c = self.canvas
        for t, d in deg.items():
            x, y = _px(t)
            if d >= 3:
                c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=COL_WIRE, outline=COL_WIRE)
            elif d == 1:
                c.create_oval(x - 4, y - 4, x + 4, y + 4, outline='#dc2626', width=1.5)

    def _draw_node_labels(self, net_of, names):
        """Node name (and voltage after Solve) at the top-left point of each node."""
        anchor = {}
        for pt, root in net_of.items():
            if root not in anchor or (pt[1], pt[0]) < (anchor[root][1], anchor[root][0]):
                anchor[root] = pt
        volts = self.results[0] if self.results else {}
        prefix = 'peak ' if self.results and self.tran_labels else ''
        c = self.canvas
        placed = []
        for root, pt in sorted(anchor.items(), key=lambda kv: (kv[1][1], kv[1][0])):
            name = names[root]
            if name == '0':
                continue
            x, y = _px(pt)
            # up-left of the node, away from part labels (which sit below/right)
            if name in volts:
                t = c.create_text(x - 6, y - 5, text=f'{name}: {prefix}{eng(volts[name], "V")}', anchor='se',
                                  fill=COL_RESULT, font=('Helvetica', 10, 'bold'))
            else:
                t = c.create_text(x - 6, y - 4, text=name, anchor='se', fill=COL_NODE,
                                  font=('Helvetica', 9, 'italic'))
            x0, y0, x1, y1 = c.bbox(t)
            for _ in range(6):           # move up while it overlaps an earlier label
                hit = [b for b in placed if x0 < b[2] and b[0] < x1 and y0 < b[3] and b[1] < y1]
                if not hit:
                    break
                dy = y1 - min(b[1] for b in hit) + 2
                c.move(t, 0, -dy)
                x0, y0, x1, y1 = c.bbox(t)
            placed.append((x0, y0, x1, y1))
            bg = c.create_rectangle(x0 - 2, y0, x1 + 2, y1, fill='white', outline='')
            c.tag_lower(bg, t)

    def _draw_ghost(self):
        c = self.canvas
        if self.tool in PLACE_TOOLS:
            gx, gy = self.mouse
            draw_part(c, Part(self.tool, gx, gy, self.rot if self.tool in TWO_TERMINAL else 0,
                              name='', value=' '), COL_GHOST)
        elif self.tool == 'wire' and self.wire_start:
            a, b = self.wire_start, self.mouse
            corner = (b[0], a[1])
            c.create_line(*_px(a), *_px(corner), *_px(b), fill=COL_GHOST, width=2, dash=(4, 3))

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------
    def solve(self):
        errs = self.sch.check()
        if errs:
            self._show_output('Cannot solve yet:\n  ' + '\n  '.join(errs))
            return
        if not self.solver or not os.path.isfile(self.solver):
            if not self.choose_solver():
                return
        opts = []
        if self.opt_matrix.get():
            opts.append('--matrix')
        self.status.set('Solving…')
        self.root.update_idletasks()
        res = run_solver(self.solver, self.sch.netlist(), opts)

        tran = res.get('tran')
        if tran:   # keep the comment lines; the data go to the plot
            text = '\n'.join(l for l in res['stdout'].splitlines() if l.startswith('#'))
            text += f"\n{len(tran['rows'])} time points -- see the plot window.\nValues at the end time:\n"
            text += '\n'.join(f'  {c} = {v:.6g}' for c, v in zip(tran['cols'], tran['rows'][-1][1:])) \
                if tran['rows'] else ''
        else:
            text = res['stdout']
        if res['stderr']:
            text += ('\n' if text else '') + res['stderr']

        if res['ok']:
            self.results = (res['volts'], res['amps'])
            self.tran_labels = bool(tran)
            if tran:
                self.tran = tran
                peaks = {}
                for k, col in enumerate(tran['cols']):
                    if col.startswith('V('):
                        peaks[col[2:-1]] = max(abs(r[k + 1]) for r in tran['rows'])
                self.results = (peaks, res['amps'])
                self.status.set('Transient done. The drawing shows each node’s peak |V|; waveforms are in the plot.')
                self.show_plot()
            else:
                text += '\n' + self._branch_report(res['volts'], res['amps'])
                self.status.set('Solved. Node voltages are shown in red on the drawing.')
        else:
            self.results = None
            self.status.set('Solver reported an error -- see Results.')
        self._show_output(text)
        self.redraw()

    def _branch_report(self, volts, amps):
        """DC current in every part, computed here from the node voltages."""
        net_of, names = self.sch.nets()
        lines = ['Branch currents (n+ → n- through the part):']
        for p in sorted((q for q in self.sch.parts if q.kind != 'GND'), key=lambda q: q.name):
            nodes = [names[net_of[t]] for t in p.terminals()]
            V = [volts.get(n, 0.0) for n in nodes]
            if p.kind == 'R':
                i = (V[0] - V[1]) / parse_value(p.value)
            elif p.kind == 'C':
                i = 0.0
            elif p.kind == 'I':
                i = parse_source(p.value)[1][0]
            elif p.kind == 'G':
                i = parse_value(p.value) * (V[2] - V[3])
            else:                                   # V, E, L: solved for directly
                i = amps.get(p.name, float('nan'))
            lines.append(f'  {p.name:5s} {eng(i, "A"):>12s}   ({nodes[0]} → {nodes[1]})')
        return '\n'.join(lines)

    def show_plot(self):
        if not self.tran:
            self.status.set('No transient results yet: choose Analysis > Transient and solve.')
            return
        if self.plot is None or not self.plot.winfo_exists():
            self.plot = PlotWindow(self.root)
        self.plot.set_data(self.tran)
        self.plot.lift()

    def _show_output(self, text):
        self.out_text.delete('1.0', 'end')
        self.out_text.insert('1.0', text)

    def choose_solver(self):
        path = filedialog.askopenfilename(title='Choose the solver program you built (solver or solver.exe)')
        if path:
            self.solver = path
            self.status.set(f'Solver: {path}')
            return True
        return False

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def new(self):
        self.sch, self.file, self.selected, self.results = Schematic(), None, None, None
        self.refresh()

    def open(self, path=None):
        path = path or filedialog.askopenfilename(filetypes=[('Schematic', '*.json'), ('All files', '*')])
        if not path:
            return
        try:
            self.sch = Schematic.load(path)
        except Exception as ex:      # noqa: BLE001 -- show any load error to the user
            messagebox.showerror('Open', f'Could not open {path}:\n{ex}')
            return
        self.file, self.selected, self.results = path, None, None
        self.root.title(f'ECE 3340 Circuit Solver -- {os.path.basename(path)}')
        self.refresh()

    def save(self, ask=False):
        if ask or not self.file:
            path = filedialog.asksaveasfilename(defaultextension='.json',
                                                filetypes=[('Schematic', '*.json')])
            if not path:
                return
            self.file = path
        self.sch.save(self.file)
        self.root.title(f'ECE 3340 Circuit Solver -- {os.path.basename(self.file)}')

    def export_netlist(self):
        path = filedialog.asksaveasfilename(defaultextension='.cir',
                                            filetypes=[('Netlist', '*.cir')])
        if path:
            with open(path, 'w') as f:
                f.write(self.sch.netlist())


# ----------------------------------------------------------------------
# Waveform plot
# ----------------------------------------------------------------------
def nice_ticks(lo, hi, n=6):
    """About n round-numbered ticks covering [lo, hi]."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    return [first + k * step for k in range(int((hi - first) / step + 1e-9) + 1)]


class PlotWindow(tk.Toplevel):
    """Line plot of transient results; tick a trace on the right to show it."""
    W, H = 760, 460
    ML, MR, MT, MB = 80, 20, 20, 50

    def __init__(self, master):
        super().__init__(master)
        self.title('Transient waveforms')
        self.canvas = tk.Canvas(self, width=self.W, height=self.H, bg='white', highlightthickness=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.side = ttk.Frame(self, padding=6)
        self.side.pack(side='right', fill='y')
        self.vars = {}
        self.data = None

    def set_data(self, tran):
        self.data = tran
        for w in self.side.winfo_children():
            w.destroy()
        ttk.Label(self.side, text='Show:').pack(anchor='w')
        old = {k: v.get() for k, v in self.vars.items()}
        self.vars = {}
        nv = 0
        for k, name in enumerate(tran['cols']):
            default = name.startswith('V(') and nv < 4
            nv += name.startswith('V(')
            var = tk.BooleanVar(value=old.get(name, default))
            self.vars[name] = var
            tk.Checkbutton(self.side, text=name, variable=var, command=self.redraw,
                           fg=TRACE_COLORS[k % len(TRACE_COLORS)], anchor='w').pack(fill='x')
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete('all')
        if not self.data or not self.data['rows']:
            return
        rows, cols = self.data['rows'], self.data['cols']
        shown = [k for k, name in enumerate(cols) if self.vars[name].get()]
        t = [r[0] for r in rows]
        t0, t1 = 0.0, t[-1]
        ys = [r[k + 1] for r in rows for k in shown] or [0.0, 1.0]
        y0, y1 = min(ys), max(ys)
        pad = 0.08 * (y1 - y0) if y1 > y0 else max(abs(y0), 1.0) * 0.1
        y0, y1 = y0 - pad, y1 + pad
        L, R, T, B = self.ML, self.W - self.MR, self.MT, self.H - self.MB

        def X(v):
            return L + (v - t0) / (t1 - t0) * (R - L)

        def Y(v):
            return B - (v - y0) / (y1 - y0) * (B - T)

        units = {cols[k][0] for k in shown}
        yunit = 'V' if units == {'V'} else 'A' if units == {'I'} else ''
        for v in nice_ticks(y0, y1):
            c.create_line(L, Y(v), R, Y(v), fill='#e5e7eb')
            c.create_text(L - 6, Y(v), text=eng(v, yunit), anchor='e', font=('Helvetica', 9))
        for v in nice_ticks(t0, t1):
            c.create_line(X(v), T, X(v), B, fill='#e5e7eb')
            c.create_text(X(v), B + 6, text=eng(v, 's'), anchor='n', font=('Helvetica', 9))
        if y0 < 0 < y1:
            c.create_line(L, Y(0), R, Y(0), fill='#9ca3af')
        c.create_rectangle(L, T, R, B, outline='#6b7280')
        c.create_text((L + R) / 2, self.H - 14, text='time', font=('Helvetica', 10))

        step = max(1, len(rows) // 1500)          # enough points for a smooth line
        for k in shown:
            pts = []
            for r in rows[::step] + ([rows[-1]] if (len(rows) - 1) % step else []):
                pts += [X(r[0]), Y(r[k + 1])]
            if len(pts) >= 4:
                c.create_line(*pts, fill=TRACE_COLORS[k % len(TRACE_COLORS)], width=2)


# ----------------------------------------------------------------------
# Drawing helpers
# ----------------------------------------------------------------------
def _px(pt):
    return pt[0] * GRID, pt[1] * GRID


def _seg_dist(px, py, a, b):
    ax, ay = _px(a)
    bx, by = _px(b)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _value_text(p):
    if p.kind in SOURCES:
        src = parse_source(p.value)
        if src is None:
            return f'{p.value}?'
        return eng(src[1][0], UNITS[p.kind]) if src[0] == 'DC' else p.value.strip()
    v = parse_value(p.value)
    return eng(v, UNITS[p.kind]) if v is not None else f'{p.value}?'


def draw_part(c, p, col):
    """Draw one part on canvas c."""
    if p.kind == 'GND':
        x, y = _px((p.x, p.y))
        c.create_line(x, y, x, y + 0.5 * GRID, fill=col, width=2)
        for k, half in enumerate((0.45, 0.28, 0.11)):
            yy = y + (0.5 + 0.15 * k) * GRID
            c.create_line(x - half * GRID, yy, x + half * GRID, yy, fill=col, width=2)
        return

    if p.kind in FOUR_TERMINAL:
        _draw_controlled(c, p, col)
        return

    (x1, y1), (x2, y2) = (_px(t) for t in p.terminals())
    ux, uy = DIRS[p.rot]                  # along the part, n+ -> n-
    vx, vy = -uy, ux                      # sideways
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2

    def P(s, t):                          # point at s along, t sideways (pixels from middle)
        return mx + s * ux + t * vx, my + s * uy + t * vy

    def leads(h):
        c.create_line(x1, y1, *P(-h, 0), fill=col, width=2)
        c.create_line(*P(h, 0), x2, y2, fill=col, width=2)

    if p.kind == 'R':
        h = 0.6 * GRID
        leads(h)
        pts = [P(-h, 0)]
        for k in range(6):
            pts.append(P(-h + (k + 0.5) * 2 * h / 6, (0.22 if k % 2 == 0 else -0.22) * GRID))
        pts.append(P(h, 0))
        c.create_line(*[v for xy in pts for v in xy], fill=col, width=2)
    elif p.kind == 'C':
        h, w = 0.12 * GRID, 0.4 * GRID
        leads(h)
        c.create_line(*P(-h, -w), *P(-h, w), fill=col, width=3)
        c.create_line(*P(h, -w), *P(h, w), fill=col, width=3)
    elif p.kind == 'L':
        h = 0.65 * GRID
        leads(h)
        pts = []
        for k in range(41):                # four humps
            s = -h + 2 * h * k / 40
            pts.append(P(s, -0.28 * GRID * abs(math.sin(4 * math.pi * k / 40))))
        c.create_line(*[v for xy in pts for v in xy], fill=col, width=2, smooth=True)
    else:                                   # V or I: a circle
        rr = 0.55 * GRID
        leads(rr)
        c.create_oval(mx - rr, my - rr, mx + rr, my + rr, outline=col, width=2)
        if p.kind == 'I':
            c.create_line(*P(-0.6 * rr, 0), *P(0.6 * rr, 0), fill=col, width=2, arrow='last',
                          arrowshape=(8, 9, 4))
        else:
            c.create_text(*P(-0.45 * rr, 0), text='+', fill=col, font=('Helvetica', 12, 'bold'))
            c.create_text(*P(0.45 * rr, 0), text='−', fill=col, font=('Helvetica', 12, 'bold'))

    if p.name:
        label = f'{p.name}\n{_value_text(p)}'
        # label below a horizontal part, to the right of a vertical one
        if p.rot in (0, 2):
            c.create_text(mx, my + 0.95 * GRID, text=label, fill=col, font=('Helvetica', 9),
                          justify='center')
        else:
            c.create_text(mx + 0.75 * GRID, my, text=label, anchor='w', fill=col,
                          font=('Helvetica', 9), justify='left')


def _draw_controlled(c, p, col):
    """VCVS / VCCS: control + and - on the left, diamond output on the right."""
    op, om, cp, cm = (_px(t) for t in p.terminals())
    mx, my = op[0], (op[1] + om[1]) / 2
    d = 0.55 * GRID
    c.create_line(*op, mx, my - d, fill=col, width=2)
    c.create_line(mx, my + d, *om, fill=col, width=2)
    c.create_polygon(mx, my - d, mx + d, my, mx, my + d, mx - d, my, outline=col, fill='', width=2)
    if p.kind == 'E':
        c.create_text(mx, my - 0.45 * d, text='+', fill=col, font=('Helvetica', 11, 'bold'))
        c.create_text(mx, my + 0.45 * d, text='−', fill=col, font=('Helvetica', 11, 'bold'))
    else:
        c.create_line(mx, my - 0.6 * d, mx, my + 0.6 * d, fill=col, width=2, arrow='last',
                      arrowshape=(7, 8, 3))
    # control terminals: short stubs with + / - and a dashed link to the diamond
    for (x, y), sign in ((cp, '+'), (cm, '−')):
        c.create_line(x, y, x + 0.45 * GRID, y, fill=col, width=2)
        c.create_text(x + 0.62 * GRID, y, text=sign, fill=col, font=('Helvetica', 11, 'bold'))
    c.create_line(cp[0] + 0.8 * GRID, my, mx - d - 4, my, fill=col, dash=(3, 3))
    c.create_line(cp[0] + 0.8 * GRID, cp[1] + 0.3 * GRID, cp[0] + 0.8 * GRID, cm[1] - 0.3 * GRID,
                  fill=col, dash=(3, 3))
    if p.name:
        c.create_text(mx + 0.75 * GRID, my, text=f'{p.name}\n{_value_text(p)}', anchor='w',
                      fill=col, font=('Helvetica', 9), justify='left')


def main():
    root = tk.Tk()
    CircuitGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
