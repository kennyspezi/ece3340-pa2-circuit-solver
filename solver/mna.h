/*
 * mna.h  --  MODULE 2: turn a netlist into the linear system A x = b
 * using Modified Nodal Analysis (MNA). PROVIDED.
 *
 * Unknowns x (in this order):
 *   x[0 .. N-1]   node voltages (ground excluded)
 *   x[N .. ]      branch currents of every V source, E source and inductor,
 *                 in netlist order
 *
 * Rows of A: KCL at each node, then one equation per branch current.
 *
 * Stamps (g = 1/R; a, b = n+, n-; c, d = control nodes; m = branch row/column;
 * skip any index that is ground):
 *
 *   R          A[a][a] += g   A[a][b] -= g   A[b][a] -= g   A[b][b] += g
 *   I          rhs[a] -= I(t)                rhs[b] += I(t)
 *   V          A[a][m] += 1   A[b][m] -= 1   A[m][a] += 1   A[m][b] -= 1   rhs[m] = V(t)
 *   G (VCCS)   A[a][c] += gm  A[a][d] -= gm  A[b][c] -= gm  A[b][d] += gm
 *   E (VCVS)   like V, plus   A[m][c] -= gain   A[m][d] += gain,   rhs[m] = 0
 *
 * Capacitors and inductors depend on the analysis:
 *
 *   DC:         C is an open circuit (no stamp).
 *               L is a short: like a 0 V source, V(a) - V(b) = 0.
 *
 *   Transient, backward Euler with step h (x_prev = solution at t - h):
 *     C:  i = C (v - v_prev) / h  ->  a resistor with g = C/h, plus
 *         rhs[a] += (C/h) v_prev,  rhs[b] -= (C/h) v_prev
 *     L:  v = L (i - i_prev) / h  ->  like V, plus A[m][m] -= L/h,
 *         rhs[m] = -(L/h) i_prev
 *
 * With a fixed step h, A is THE SAME at every time step. Only the right-hand
 * side changes. So the solver factors A once and reuses L, U, P.
 */
#ifndef MNA_H
#define MNA_H

#include "netlist.h"
#include <string>
#include <vector>

struct MnaSystem {
    int n = 0;                       /* number of unknowns               */
    int num_nodes = 0;               /* N                                */
    bool tran = false;               /* transient (true) or DC (false)   */
    double h = 0;                    /* time step (transient)            */
    std::vector<double> A;           /* n x n, row-major (see plu.h)     */
    std::vector<double> rhs;         /* length n                         */
    std::vector<std::string> label;  /* "V(out)", "I(V1)", ...           */
    std::vector<int> branch;         /* per element: its current's index, or -1 */
};

/* Build A (and the right-hand side at t = 0 from rest).
 * tran = false: DC operating point. tran = true: backward Euler with step h. */
void build_mna(const Netlist &net, MnaSystem &sys, bool tran = false, double h = 0.0);

/* Right-hand side at time t, given the previous solution (transient only;
 * for DC pass t = 0 and an all-zero xprev). A is not touched. */
void build_rhs(const Netlist &net, MnaSystem &sys, double t, const std::vector<double> &xprev);

#endif /* MNA_H */
