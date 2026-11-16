/*
 * plu.h  --  ECE 3340 Circuit Solver Project
 *
 * The interface between the circuit solver framework and YOUR code.
 * You implement the three functions marked "STUDENT" in plu_student.cpp.
 * Do not change these prototypes: the framework and the GUI
 * call them exactly as written here.
 *
 * Matrix storage convention (used everywhere in this project):
 *   An n x n matrix is a single array of n*n doubles in ROW-MAJOR order,
 *   so entry (i, j) -- row i, column j, both starting at 0 -- is A[i*n + j].
 */
#ifndef PLU_H
#define PLU_H

/* ------------------------------------------------------------------ */
/* STUDENT: LU factorization with partial pivoting, P A = L U          */
/* ------------------------------------------------------------------ */
/*
 * Input:
 *   n   size of the matrix
 *   A   n x n matrix (row-major). It is OVERWRITTEN with the factors:
 *         - on and above the diagonal: U
 *         - below the diagonal:        the multipliers l_ij of L
 *       L has ones on its diagonal; those ones are NOT stored.
 *   p   array of length n, filled in by you. It records the row swaps:
 *         row i of (P A) is row p[i] of the original A.
 *       (Start with p[i] = i and swap entries of p whenever you swap rows.)
 *
 * Return value:
 *   0      success
 *   k + 1  the matrix is singular: at elimination step k (0-based) every
 *          candidate pivot in column k was exactly zero.
 *
 * Partial pivoting: at step k, choose the row r >= k with the largest
 * |A[r][k]|, swap rows r and k (the whole row, including stored
 * multipliers), then eliminate below the pivot.
 */
int plu_factor(int n, double *A, int *p);

/* ------------------------------------------------------------------ */
/* STUDENT: forward substitution, solve L y = c                        */
/* ------------------------------------------------------------------ */
/*
 * LU  the factored matrix from plu_factor (only the part below the
 *     diagonal is used; L's diagonal is 1)
 * c   right-hand side, length n (already permuted: c = P b)
 * y   output, length n
 */
void forward_sub(int n, const double *LU, const double *c, double *y);

/* ------------------------------------------------------------------ */
/* STUDENT: back substitution, solve U x = y                           */
/* ------------------------------------------------------------------ */
/*
 * LU  the factored matrix from plu_factor (the part on and above the
 *     diagonal is U)
 * y   right-hand side, length n
 * x   output, length n
 */
void back_sub(int n, const double *LU, const double *y, double *x);

/* ------------------------------------------------------------------ */
/* PROVIDED (in plu_library.cpp): the same three functions, done by the */
/* Eigen library. main.cpp uses these until you set USE_MY_PLU to 1.    */
/* ------------------------------------------------------------------ */
int  lib_plu_factor(int n, double *A, int *p);
void lib_forward_sub(int n, const double *LU, const double *c, double *y);
void lib_back_sub(int n, const double *LU, const double *y, double *x);

#endif /* PLU_H */
