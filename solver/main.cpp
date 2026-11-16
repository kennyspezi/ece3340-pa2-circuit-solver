/*
 * main.cpp  --  MODULE 4: the "solver" program. PROVIDED.
 *
 * Step 3 (factor and solve) is done by a library PLU until you switch to
 * your own: set USE_MY_PLU below to 1 and run make again.
 *
 *   netlist file --(module 1)--> elements --(module 2)--> A x = b
 *                --(module 3, YOUR PLU)--> x --> printed results
 *
 * Usage:
 *   solver [options] circuit.cir
 *
 * Option:
 *   --matrix    also print A and b (b at t = 0 for a transient)
 *
 * Output, DC (no .tran line):         Output, transient (.tran step stop):
 *   V(<node>) = <volts>                 # comment lines
 *   I(<source>) = <amps>                time V(n1) V(n2) ... I(V1) ...
 *                                       <t> <value> <value> ...   (one row per step)
 *
 * Exit status: 0 = solved, 1 = bad input, 2 = singular matrix.
 */
#include "mna.h"
#include "netlist.h"
#include "plu.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

/* 0: library PLU (Eigen, plu_library.cpp)    1: YOUR PLU (plu_student.cpp) */
#define USE_MY_PLU 0

#if USE_MY_PLU
#define PLU_FACTOR  plu_factor
#define FORWARD_SUB forward_sub
#define BACK_SUB    back_sub
#define PLU_NAME    "your PLU"
#else
#define PLU_FACTOR  lib_plu_factor
#define FORWARD_SUB lib_forward_sub
#define BACK_SUB    lib_back_sub
#define PLU_NAME    "library PLU"
#endif

using Clock = std::chrono::steady_clock;

/* Solve A x = b with the factors: c = P b, then L y = c, then U x = y. */
static void solve_factored(int n, const double *LU, const int *p, const double *b, double *x)
{
    std::vector<double> c(n), y(n);
    for (int i = 0; i < n; ++i) c[i] = b[p[i]];
    FORWARD_SUB(n, LU, c.data(), y.data());
    BACK_SUB(n, LU, y.data(), x);
}

static double ms_since(Clock::time_point t0)
{
    return 1e3 * std::chrono::duration<double>(Clock::now() - t0).count();
}

static void print_system(const MnaSystem &sys)
{
    const int n = sys.n;
    std::printf("# A (%d x %d) and b:\n", n, n);
    for (int i = 0; i < n; ++i) {
        std::printf("#  ");
        for (int j = 0; j < n; ++j) std::printf("%11.4g ", sys.A[(size_t)i * n + j]);
        std::printf("| %11.4g   <- %s %s\n", sys.rhs[i],
                    i < sys.num_nodes ? "KCL at" : "equation of", sys.label[i].c_str());
    }
}

/* Factor A into LU and p. Returns 0, or prints why not. */
static int factor(const MnaSystem &sys, std::vector<double> &LU, std::vector<int> &p)
{
    const int n = sys.n;
    LU = sys.A;
    p.assign(n, 0);
    int info = PLU_FACTOR(n, LU.data(), p.data());
    if (info < 0) {
        std::fprintf(stderr, "ERROR: plu_factor returned %d -- not implemented yet?\n", info);
        return 2;
    }
    if (info > 0) {
        std::fprintf(stderr, "ERROR: zero pivot at elimination step %d (unknown %s).\n",
                     info - 1, sys.label[info - 1].c_str());
        std::fprintf(stderr, "       The matrix is singular. Look for: nodes not connected to ground,\n"
                                 "       a loop of voltage sources or inductors, or (DC only) a node\n"
                                 "       connected only through capacitors.\n");
        return 2;
    }
    return 0;
}

int main(int argc, char **argv)
{
    bool show_matrix = false;
    const char *file = nullptr;

    for (int i = 1; i < argc; ++i) {
        if (!std::strcmp(argv[i], "--matrix")) show_matrix = true;
        else if (argv[i][0] == '-' && argv[i][1] == '-') {
            std::fprintf(stderr, "ERROR: unknown option %s\n", argv[i]);
            return 1;
        }
        else file = argv[i];
    }
    if (!file) {
        std::fprintf(stderr, "usage: solver [--matrix] circuit.cir\n");
        return 1;
    }

    /* Module 1: read the netlist */
    Netlist net;
    if (!read_netlist(file, net)) return 1;
    if (!net.has_ground) {
        std::fprintf(stderr, "ERROR: no ground node. Connect something to node 0 (gnd).\n");
        return 1;
    }

    /* Module 2: build A x = b */
    MnaSystem sys;
    build_mna(net, sys, net.tran, net.tran_step);
    const int n = sys.n;
    std::printf("# %d nodes, %d unknowns, %s, %s\n", sys.num_nodes, n,
                net.tran ? "transient (backward Euler)" : "DC", PLU_NAME);
    std::fflush(stdout);
    if (show_matrix) print_system(sys);

    /* Module 3: factor once */
    std::vector<double> LU, x(n);
    std::vector<int> p;
    auto t0 = Clock::now();
    int status = factor(sys, LU, p);
    double t_factor = ms_since(t0);
    if (status) return status;

    if (!net.tran) {
        solve_factored(n, LU.data(), p.data(), sys.rhs.data(), x.data());
        for (int i = 0; i < n; ++i)
            std::printf("%s = %.10g\n", sys.label[i].c_str(), x[i]);
        return 0;
    }

    /* Transient: same A every step, so reuse the factors. Start from rest. */
    const double h = net.tran_step;
    const long steps = (long)std::floor(net.tran_stop / h + 0.5);
    if (steps > 1000000) {
        std::fprintf(stderr, "ERROR: %ld time steps is too many; use a larger step.\n", steps);
        return 1;
    }
    const long stride = steps > 4000 ? (steps + 3999) / 4000 : 1;   /* print at most ~4000 rows */

    std::printf("time");
    for (int i = 0; i < n; ++i) std::printf(" %s", sys.label[i].c_str());
    std::printf("\n");

    std::vector<double> xprev(n, 0.0);
    t0 = Clock::now();
    for (long k = 1; k <= steps; ++k) {
        const double t = k * h;
        build_rhs(net, sys, t, xprev);
        solve_factored(n, LU.data(), p.data(), sys.rhs.data(), x.data());
        if (k % stride == 0 || k == steps) {
            std::printf("%.6g", t);
            for (int i = 0; i < n; ++i) std::printf(" %.8g", x[i]);
            std::printf("\n");
        }
        xprev.swap(x);
    }
    double t_solve = ms_since(t0);
    std::printf("# factored A once (%.3f ms), then %ld solves (%.3f ms total)\n",
                t_factor, steps, t_solve);
    return 0;
}
