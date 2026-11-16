ECE 3340 Project: a circuit solver powered by your PLU
=======================================================
```
solver/      the C++ program
  plu.h            the three functions you write: read this first
  plu_student.cpp  YOUR CODE: plu_factor, forward_sub, back_sub
  plu_library.cpp  the same three functions, done by the Eigen library
  netlist.*        reads a netlist file (.cir) into a list of parts
  mna.*            builds A x = b from the parts
  main.cpp         runs everything; USE_MY_PLU (line 35) picks the PLU
  Makefile         build on macOS / Linux: type make
lib/Eigen/   the Eigen library (header files only; nothing to install)
gui/         the drawing program (Python 3): run circuit_gui.py
examples/    netlists (.cir) and drawings (.json); the comment lines at
             the top of each .cir file say what it shows
```

Build in Dev-C++ (Windows)
  1. File > New > Project > Empty Project, named solver; save it in the
     solver folder.
  2. Project > Add to Project: main.cpp, netlist.cpp, mna.cpp,
     plu_library.cpp, plu_student.cpp.
  3. Project > Project Options: type Win32 Console; C++ compiler: -std=c++11.
  4. Execute > Compile. This makes solver/solver.exe.
  5. Execute > Parameters: ..\examples\<name>.cir, then Execute > Run.

Use your own PLU
  Write the three functions in plu_student.cpp, set USE_MY_PLU to 1 in
  main.cpp, and compile again. The first line of the output changes from
  "library PLU" to "your PLU". Both must give the same numbers.

Draw circuits
  Double-click gui/circuit_gui.py (or: python circuit_gui.py). Draw parts
  and wires, place a ground, click Solve.
