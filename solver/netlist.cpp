/*
 * netlist.cpp  --  MODULE 1 implementation. PROVIDED.
 */
#include "netlist.h"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <sstream>

static const double PI = 3.14159265358979323846;
static const double INF = std::numeric_limits<double>::infinity();

static std::string lower(std::string s)
{
    for (char &c : s) c = (char)std::tolower((unsigned char)c);
    return s;
}

static bool is_ground(const std::string &name)
{
    std::string s = lower(name);
    return s == "0" || s == "gnd";
}

/* ------------------------------------------------------------------ */
/* Waveforms                                                           */
/* ------------------------------------------------------------------ */
double Waveform::at(double t) const
{
    switch (kind) {
    case DC:
        return p[0];
    case PULSE: {
        const double v1 = p[0], v2 = p[1], td = p[2], tr = p[3], tf = p[4], pw = p[5], per = p[6];
        if (t < td) return v1;
        double tt = t - td;
        if (per > 0 && per < INF) tt = std::fmod(tt, per);
        if (tt < tr) return v1 + (v2 - v1) * tt / tr;
        tt -= tr;
        if (tt < pw) return v2;
        tt -= pw;
        if (tt < tf) return v2 + (v1 - v2) * tt / tf;
        return v1;
    }
    case SIN: {
        const double vo = p[0], va = p[1], f = p[2], td = p[3];
        if (t < td) return vo;
        return vo + va * std::sin(2 * PI * f * (t - td));
    }
    }
    return 0.0;
}

/* "PULSE(0 5 1m)", "SIN(0 1 1k)", "DC 5", "5"  ->  Waveform */
static bool parse_source(std::string text, Waveform &w, std::string &err)
{
    for (char &c : text) if (c == '(' || c == ')' || c == ',') c = ' ';
    std::istringstream ss(text);
    std::vector<std::string> tok;
    std::string s;
    while (ss >> s) tok.push_back(s);
    if (tok.empty()) { err = "missing source value"; return false; }

    std::string kw = lower(tok[0]);
    std::vector<double> v;
    size_t first = (kw == "dc" || kw == "pulse" || kw == "sin") ? 1 : 0;
    for (size_t k = first; k < tok.size(); ++k) {
        double x;
        if (!parse_value(tok[k], x)) { err = "bad number '" + tok[k] + "'"; return false; }
        v.push_back(x);
    }

    if (kw == "pulse") {
        if (v.size() < 2 || v.size() > 7) { err = "PULSE needs 2 to 7 numbers: v1 v2 [td tr tf pw per]"; return false; }
        w.kind = Waveform::PULSE;
        double def[7] = {0, 0, 0, 0, 0, INF, INF};
        for (int k = 0; k < 7; ++k) w.p[k] = (k < (int)v.size()) ? v[k] : def[k];
        return true;
    }
    if (kw == "sin") {
        if (v.size() < 3 || v.size() > 4) { err = "SIN needs 3 or 4 numbers: vo va freq [td]"; return false; }
        w.kind = Waveform::SIN;
        for (int k = 0; k < 4; ++k) w.p[k] = (k < (int)v.size()) ? v[k] : 0.0;
        return true;
    }
    if (v.size() != 1) { err = "expected one value, PULSE(...) or SIN(...)"; return false; }
    w.kind = Waveform::DC;
    w.p[0] = v[0];
    return true;
}

/* ------------------------------------------------------------------ */
/* Netlist                                                             */
/* ------------------------------------------------------------------ */
int Netlist::node_index(const std::string &name)
{
    if (is_ground(name)) { has_ground = true; return -1; }
    for (size_t k = 0; k < node_names.size(); ++k)
        if (node_names[k] == name) return (int)k;
    node_names.push_back(name);
    return (int)node_names.size() - 1;
}

void Netlist::add(ElementType t, const std::string &name,
                  const std::string &np, const std::string &nm, double value)
{
    Element e;
    e.type = t;
    e.name = name;
    e.nplus = node_index(np);
    e.nminus = node_index(nm);
    e.value = value;
    e.wave.kind = Waveform::DC;
    e.wave.p[0] = value;
    elements.push_back(e);
}

bool parse_value(const std::string &s, double &value)
{
    const char *start = s.c_str();
    char *end = nullptr;
    double v = std::strtod(start, &end);
    if (end == start) return false;

    std::string suffix = lower(std::string(end));
    double scale = 1.0;
    if (suffix.compare(0, 3, "meg") == 0) scale = 1e6;
    else if (!suffix.empty()) {
        switch (suffix[0]) {
            case 'f': scale = 1e-15; break;
            case 'p': scale = 1e-12; break;
            case 'n': scale = 1e-9;  break;
            case 'u': scale = 1e-6;  break;
            case 'm': scale = 1e-3;  break;
            case 'k': scale = 1e3;   break;
            case 'g': scale = 1e9;   break;
            case 't': scale = 1e12;  break;
            default:  scale = 1.0;   break;   /* unit letters like "V", "A", "ohm" */
        }
    }
    value = v * scale;
    return true;
}

bool read_netlist(const std::string &filename, Netlist &net)
{
    std::ifstream in(filename);
    if (!in) {
        std::fprintf(stderr, "ERROR: cannot open netlist file '%s'\n", filename.c_str());
        return false;
    }

    std::string line;
    int lineno = 0;
    while (std::getline(in, line)) {
        ++lineno;
        size_t semi = line.find(';');
        if (semi != std::string::npos) line.erase(semi);

        std::istringstream ss(line);
        std::string name;
        if (!(ss >> name)) continue;                        /* blank line */
        char c0 = name[0];
        if (c0 == '*' || c0 == '#') continue;               /* comment     */
        std::string lname = lower(name);
        if (lname == ".end") break;
        if (lname == ".tran") {
            std::string a, b;
            if (!(ss >> a >> b) || !parse_value(a, net.tran_step) || !parse_value(b, net.tran_stop) ||
                !(net.tran_step > 0) || !(net.tran_stop > net.tran_step)) {
                std::fprintf(stderr, "ERROR line %d: expected '.tran <step> <stop>' with 0 < step < stop\n", lineno);
                return false;
            }
            net.tran = true;
            continue;
        }
        if (c0 == '.') continue;                            /* other dot commands ignored */

        ElementType t;
        int nnodes = 2;
        switch (std::toupper((unsigned char)c0)) {
            case 'R': t = ELEM_R; break;
            case 'C': t = ELEM_C; break;
            case 'L': t = ELEM_L; break;
            case 'V': t = ELEM_V; break;
            case 'I': t = ELEM_I; break;
            case 'E': t = ELEM_E; nnodes = 4; break;
            case 'G': t = ELEM_G; nnodes = 4; break;
            default:
                std::fprintf(stderr, "ERROR line %d: unknown element '%s' "
                             "(supported: R C L V I E G)\n", lineno, name.c_str());
                return false;
        }

        std::string nodes[4];
        for (int k = 0; k < nnodes; ++k) {
            if (!(ss >> nodes[k])) {
                std::fprintf(stderr, "ERROR line %d: %s needs %d node names and a value\n",
                             lineno, name.c_str(), nnodes);
                return false;
            }
        }
        std::string rest, tok;
        while (ss >> tok) rest += (rest.empty() ? "" : " ") + tok;
        if (rest.empty()) {
            std::fprintf(stderr, "ERROR line %d: %s has no value\n", lineno, name.c_str());
            return false;
        }

        for (const Element &e : net.elements) {
            if (lower(e.name) == lname) {
                std::fprintf(stderr, "ERROR line %d: duplicate element name '%s'\n", lineno, name.c_str());
                return false;
            }
        }

        Element e;
        e.type = t;
        e.name = name;
        if (t == ELEM_V || t == ELEM_I) {
            std::string err;
            if (!parse_source(rest, e.wave, err)) {
                std::fprintf(stderr, "ERROR line %d: %s: %s\n", lineno, name.c_str(), err.c_str());
                return false;
            }
            e.value = e.wave.at(0.0);
        } else {
            if (rest.find(' ') != std::string::npos || !parse_value(rest, e.value)) {
                std::fprintf(stderr, "ERROR line %d: bad value '%s'\n", lineno, rest.c_str());
                return false;
            }
            if ((t == ELEM_R || t == ELEM_C || t == ELEM_L) && !(e.value > 0.0)) {
                std::fprintf(stderr, "ERROR line %d: %s must be > 0\n", lineno, name.c_str());
                return false;
            }
        }
        e.nplus = net.node_index(nodes[0]);
        e.nminus = net.node_index(nodes[1]);
        if (nnodes == 4) {
            e.cplus = net.node_index(nodes[2]);
            e.cminus = net.node_index(nodes[3]);
        }
        net.elements.push_back(e);
    }

    if (net.elements.empty()) {
        std::fprintf(stderr, "ERROR: netlist '%s' has no elements\n", filename.c_str());
        return false;
    }
    return true;
}
