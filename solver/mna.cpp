/*
 * mna.cpp  --  MODULE 2 implementation. PROVIDED.
 */
#include "mna.h"

static bool has_branch(const Element &e)
{
    return e.type == ELEM_V || e.type == ELEM_E || e.type == ELEM_L;
}

void build_mna(const Netlist &net, MnaSystem &sys, bool tran, double h)
{
    const int N = net.num_nodes();

    /* number the unknowns */
    sys.label.clear();
    sys.branch.assign(net.elements.size(), -1);
    for (int k = 0; k < N; ++k) sys.label.push_back("V(" + net.node_names[k] + ")");
    int n = N;
    for (size_t k = 0; k < net.elements.size(); ++k) {
        if (has_branch(net.elements[k])) {
            sys.branch[k] = n++;
            sys.label.push_back("I(" + net.elements[k].name + ")");
        }
    }

    sys.n = n;
    sys.num_nodes = N;
    sys.tran = tran;
    sys.h = h;
    sys.A.assign((size_t)n * n, 0.0);

    auto add = [&](int i, int j, double v) {
        if (i >= 0 && j >= 0) sys.A[(size_t)i * n + j] += v;
    };

    for (size_t k = 0; k < net.elements.size(); ++k) {
        const Element &e = net.elements[k];
        const int a = e.nplus, b = e.nminus, c = e.cplus, d = e.cminus, m = sys.branch[k];

        switch (e.type) {
        case ELEM_R: {
            const double g = 1.0 / e.value;
            add(a, a, g); add(b, b, g); add(a, b, -g); add(b, a, -g);
            break;
        }
        case ELEM_C:
            if (tran) {
                const double g = e.value / h;
                add(a, a, g); add(b, b, g); add(a, b, -g); add(b, a, -g);
            }
            break;                                 /* DC: open circuit */
        case ELEM_L:
            add(a, m, 1.0); add(b, m, -1.0); add(m, a, 1.0); add(m, b, -1.0);
            if (tran) add(m, m, -e.value / h);     /* DC: short circuit */
            break;
        case ELEM_V:
            add(a, m, 1.0); add(b, m, -1.0); add(m, a, 1.0); add(m, b, -1.0);
            break;
        case ELEM_E:
            add(a, m, 1.0); add(b, m, -1.0); add(m, a, 1.0); add(m, b, -1.0);
            add(m, c, -e.value); add(m, d, e.value);
            break;
        case ELEM_G:
            add(a, c, e.value); add(a, d, -e.value); add(b, c, -e.value); add(b, d, e.value);
            break;
        case ELEM_I:
            break;                                 /* right-hand side only */
        }
    }

    build_rhs(net, sys, 0.0, std::vector<double>(n, 0.0));
}

void build_rhs(const Netlist &net, MnaSystem &sys, double t, const std::vector<double> &xprev)
{
    sys.rhs.assign(sys.n, 0.0);
    auto add = [&](int i, double v) { if (i >= 0) sys.rhs[i] += v; };
    auto volt = [&](int i) { return i >= 0 ? xprev[i] : 0.0; };

    for (size_t k = 0; k < net.elements.size(); ++k) {
        const Element &e = net.elements[k];
        const int a = e.nplus, b = e.nminus, m = sys.branch[k];
        switch (e.type) {
        case ELEM_I: {
            const double I = e.wave.at(t);
            add(a, -I); add(b, I);
            break;
        }
        case ELEM_V:
            sys.rhs[m] = e.wave.at(t);
            break;
        case ELEM_C:
            if (sys.tran) {
                const double gv = e.value / sys.h * (volt(a) - volt(b));
                add(a, gv); add(b, -gv);
            }
            break;
        case ELEM_L:
            if (sys.tran) sys.rhs[m] = -e.value / sys.h * xprev[m];
            break;
        default:
            break;
        }
    }
}
