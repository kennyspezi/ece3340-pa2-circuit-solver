/*
 * netlist.h  --  MODULE 1: read a netlist file into a list of elements.
 * PROVIDED. You do not need to change this module.
 *
 * Netlist format (a subset of SPICE), one element per line:
 *
 *     * comment line            (also: lines starting with ';' or '#')
 *     R<name> <n+> <n-> <ohms>                 resistor
 *     C<name> <n+> <n-> <farads>               capacitor
 *     L<name> <n+> <n-> <henries>              inductor
 *     V<name> <n+> <n-> <source>               independent voltage source
 *     I<name> <n+> <n-> <source>               independent current source
 *     E<name> <n+> <n-> <nc+> <nc-> <gain>     VCVS: V(n+)-V(n-) = gain*(V(nc+)-V(nc-))
 *     G<name> <n+> <n-> <nc+> <nc-> <gm>       VCCS: current gm*(V(nc+)-V(nc-))
 *     .tran <step> <stop>                      transient analysis (else: DC)
 *     .end                                     (optional)
 *
 *   <source> is one of
 *     5                                  constant (DC 5 also accepted)
 *     PULSE(v1 v2 td tr tf pw per)       v1 until td, ramp to v2 in tr, hold pw,
 *                                        ramp back in tf, repeat every per.
 *                                        Only v1 v2 are required: PULSE(0 5 1m)
 *                                        is a step from 0 to 5 at t = 1 ms.
 *     SIN(vo va freq td)                 vo + va*sin(2*pi*freq*(t-td)) for t >= td
 *
 *   Node "0" (or "gnd"/"GND") is ground. Other node names are any text.
 *   Values accept SPICE suffixes: f p n u m k meg g t (4.7k, 2m, 1meg, 10u).
 *
 * Sign conventions (same as SPICE):
 *   I and G sources: the current flows from n+ THROUGH THE SOURCE to n-.
 *   V and E sources: V(n+) - V(n-) = value; their current unknown also flows
 *   from n+ through the source to n-.
 */
#ifndef NETLIST_H
#define NETLIST_H

#include <string>
#include <vector>

enum ElementType { ELEM_R, ELEM_C, ELEM_L, ELEM_V, ELEM_I, ELEM_E, ELEM_G };

/* Value of an independent source as a function of time. */
struct Waveform {
    enum Kind { DC, PULSE, SIN } kind = DC;
    double p[7] = {0, 0, 0, 0, 0, 0, 0};   /* DC: p[0]; PULSE: v1 v2 td tr tf pw per; SIN: vo va f td */
    double at(double t) const;
};

struct Element {
    ElementType type;
    std::string name;    /* e.g. "R1" */
    int nplus;           /* node index; -1 means ground */
    int nminus;
    int cplus = -1;      /* controlling nodes (E and G only) */
    int cminus = -1;
    double value = 0;    /* ohms, farads, henries, gain or gm */
    Waveform wave;       /* V and I sources */
};

struct Netlist {
    std::vector<Element> elements;
    std::vector<std::string> node_names;   /* node_names[k] = name of node k */
    bool has_ground = false;

    bool tran = false;                     /* a .tran line was given */
    double tran_step = 0, tran_stop = 0;

    int num_nodes() const { return (int)node_names.size(); }  /* excluding ground */

    /* Index of a node name, creating it if new. Ground -> -1. */
    int node_index(const std::string &name);

    /* For building a circuit in code: R, C, L, V or I with a DC value. */
    void add(ElementType t, const std::string &name,
             const std::string &np, const std::string &nm, double value);
};

/* Read a netlist file. On error, prints a message (with the line number)
 * to stderr and returns false. */
bool read_netlist(const std::string &filename, Netlist &net);

/* Parse "4.7k", "2m", "1meg" ... Returns false if not a number. */
bool parse_value(const std::string &s, double &value);

#endif /* NETLIST_H */
