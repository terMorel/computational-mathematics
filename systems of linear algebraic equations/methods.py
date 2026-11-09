import numpy as np


def back_substitution(upper, rhs):
    x = np.zeros_like(rhs)
    for i in range(len(rhs) - 1, -1, -1):
        x[i] = (rhs[i] - upper[i, i + 1:] @ x[i + 1:]) / upper[i, i]
    return x


def pivot_threshold(a):
    return (np.finfo(float).eps * len(a)) * np.max(np.abs(a))


def gaussian_elimination(a, b):
    upper = a.copy()
    rhs = b.copy()
    threshold = pivot_threshold(a)

    for k in range(len(b)):
        pivot = k + np.argmax(np.abs(upper[k:, k]))
        if abs(upper[pivot, k]) <= threshold:
            raise ArithmeticError("матрица численно вырождена")
        upper[[k, pivot]] = upper[[pivot, k]]
        rhs[[k, pivot]] = rhs[[pivot, k]]

        factors = upper[k + 1:, k] / upper[k, k]
        upper[k + 1:, k + 1:] -= np.outer(factors, upper[k, k + 1:])
        upper[k + 1:, k] = 0.0
        rhs[k + 1:] -= factors * rhs[k]

    return back_substitution(upper, rhs)


def lu_factorization(a):
    """Разложение Дулиттла A = LU без перестановок строк."""
    lower = np.eye(len(a))
    upper = np.zeros_like(a)
    threshold = pivot_threshold(a)

    for k in range(len(a)):
        upper[k, k:] = a[k, k:] - lower[k, :k] @ upper[:k, k:]
        if abs(upper[k, k]) <= threshold:
            raise ArithmeticError("нулевой или слишком малый ведущий элемент LU без перестановок")
        lower[k + 1:, k] = (
            a[k + 1:, k] - lower[k + 1:, :k] @ upper[:k, k]
        ) / upper[k, k]

    return lower, upper


def lu_solve(a, b):
    lower, upper = lu_factorization(a)
    y = np.zeros_like(b)
    for i in range(len(b)):
        y[i] = b[i] - lower[i, :i] @ y[:i]
    return back_substitution(upper, y)


def jacobi(a, b, x):
    diagonal = a.diagonal()
    if np.any(diagonal == 0):
        raise ArithmeticError("нулевой элемент на диагонали")
    while True:
        x = x + (b - a @ x) / diagonal
        yield x


def relaxation(a, b, x, omega):
    """При omega = 1 получается метод Гаусса–Зейделя."""
    if np.any(a.diagonal() == 0):
        raise ArithmeticError("нулевой элемент на диагонали")
    while True:
        updated = x.copy()
        for i in range(len(b)):
            lower_sum = a[i, :i] @ updated[:i]
            upper_sum = a[i, i + 1:] @ x[i + 1:]
            seidel = (b[i] - lower_sum - upper_sum) / a[i, i]
            updated[i] = (1 - omega) * x[i] + omega * seidel
        x = updated
        yield x


def steepest_descent(a, b, x):
    while True:
        r = b - a @ x
        denominator = r @ (a @ r)
        if denominator <= 0:
            raise ArithmeticError("вырождение шага градиентного спуска")
        x = x + ((r @ r) / denominator) * r
        yield x


def minimum_residual(a, b, x):
    while True:
        r = b - a @ x
        ar = a @ r
        denominator = ar @ ar
        numerator = ar @ r
        if denominator == 0 or numerator == 0:
            raise ArithmeticError("нулевой шаг метода минимальных невязок")
        x = x + (numerator / denominator) * r
        yield x


def conjugate_gradient(a, b, x):
    r = b - a @ x
    direction = r.copy()
    rr = r @ r

    while True:
        product = a @ direction
        denominator = direction @ product
        if denominator <= 0:
            raise ArithmeticError("вырождение шага сопряжённых градиентов")
        alpha = rr / denominator
        x = x + alpha * direction
        yield x

        r = r - alpha * product
        next_rr = r @ r
        direction = r + (next_rr / rr) * direction
        rr = next_rr


def bicgstab(a, b, x, target):
    r = b - a @ x
    shadow = r.copy()
    direction = r.copy()
    rho = shadow @ r

    while True:
        product = a @ direction
        denominator = shadow @ product
        if rho == 0 or denominator == 0:
            raise ArithmeticError("вырождение BiCGStab при вычислении α")
        alpha = rho / denominator
        s = r - alpha * product
        half_step = x + alpha * direction
        if np.linalg.norm(s) <= target and np.linalg.norm(b - a @ half_step) <= target:
            yield half_step
            return

        t = a @ s
        denominator = t @ t
        numerator = t @ s
        if denominator == 0 or numerator == 0:
            raise ArithmeticError("вырождение BiCGStab при вычислении ω")
        omega = numerator / denominator
        x = half_step + omega * s
        yield x

        r = s - omega * t
        next_rho = shadow @ r
        beta = (next_rho / rho) * (alpha / omega)
        direction = r + beta * (direction - omega * product)
        rho = next_rho
