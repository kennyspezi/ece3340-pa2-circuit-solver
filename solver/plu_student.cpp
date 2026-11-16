/*
 * plu_student.cpp  --  ECE 3340 Circuit Solver Project
 *
 * YOUR CODE GOES HERE.
 *
 * Implement the three functions below. Read plu.h first: it explains the
 * storage convention (row-major, A[i*n + j]) and exactly what each
 * function must return.
 *
 * Rules:
 *   - Plain C/C++ only. Do not call any linear-algebra library.
 *   - Do not change the function prototypes.
 *   - You may add helper functions in this file.
 *
 * To use your code: set USE_MY_PLU to 1 near the top of main.cpp, run make,
 * then solve the examples and compare with the library answers:
 *     ./solver ../examples/03_three_nodes.cir
 */
#include "plu.h"
#include <cmath>

int plu_factor(int n, double *A, int *p)
{
    /* TODO:
     * 1. Initialize the permutation: p[i] = i.
     * 2. For each column k = 0 .. n-2:
     *      a. Find the row r (k <= r < n) with the largest |A[r*n + k]|.
     *      b. If that largest value is 0, return k + 1 (singular).
     *      c. If r != k, swap rows r and k of A (all n columns) and
     *         swap p[r] and p[k].
     *      d. For each row i below k:
     *            l = A[i][k] / A[k][k]
     *            store l in A[i][k]
     *            A[i][j] -= l * A[k][j]   for j = k+1 .. n-1
     * 3. Finally, if A[n-1][n-1] is 0, return n (singular).
     * 4. Return 0.
     */
    (void)n; (void)A; (void)p;
    return -1;   /* remove this line when you implement the function */
}

void forward_sub(int n, const double *LU, const double *c, double *y)
{
    /* TODO: solve L y = c, where L is unit lower triangular.
     *   y[i] = c[i] - sum_{j < i} L[i][j] * y[j]
     * (No division: the diagonal of L is 1.)
     */
    (void)n; (void)LU; (void)c; (void)y;
}

void back_sub(int n, const double *LU, const double *y, double *x)
{
    /* TODO: solve U x = y, where U is upper triangular.
     * Work from the last row up:
     *   x[i] = ( y[i] - sum_{j > i} U[i][j] * x[j] ) / U[i][i]
     */
    (void)n; (void)LU; (void)y; (void)x;
}
