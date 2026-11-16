/*
 * plu_library.cpp  --  PROVIDED. The same three functions as yours, done
 * by a real linear-algebra library (Eigen, in the lib folder).
 *
 * main.cpp uses these until you switch it to your own code (USE_MY_PLU).
 * Same storage and same results as plu.h describes, so you can compare.
 */
#include "plu.h"
#include "../lib/Eigen/Dense"   /* path from this file, so no include-folder setting is needed */

typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> RowMat;
typedef Eigen::Map<RowMat> MatView;
typedef Eigen::Map<const RowMat> ConstMatView;
typedef Eigen::Map<Eigen::VectorXd> VecView;
typedef Eigen::Map<const Eigen::VectorXd> ConstVecView;

int lib_plu_factor(int n, double *A, int *p)
{
    MatView M(A, n, n);
    Eigen::PartialPivLU<RowMat> lu(M);          /* P A = L U, partial pivoting */
    M = lu.matrixLU();                           /* U on/above, L below the diagonal */
    const Eigen::VectorXi &ind = lu.permutationP().indices();
    for (int i = 0; i < n; ++i) p[ind[i]] = i;   /* row i of P A = row p[i] of A */
    for (int k = 0; k < n; ++k)
        if (M(k, k) == 0.0) return k + 1;        /* singular */
    return 0;
}

void lib_forward_sub(int n, const double *LU, const double *c, double *y)
{
    VecView(y, n) = ConstMatView(LU, n, n).triangularView<Eigen::UnitLower>().solve(ConstVecView(c, n));
}

void lib_back_sub(int n, const double *LU, const double *y, double *x)
{
    VecView(x, n) = ConstMatView(LU, n, n).triangularView<Eigen::Upper>().solve(ConstVecView(y, n));
}
