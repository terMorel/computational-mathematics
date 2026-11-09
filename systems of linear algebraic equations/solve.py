import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from methods import (
    bicgstab,
    conjugate_gradient,
    gaussian_elimination,
    jacobi,
    lu_solve,
    minimum_residual,
    relaxation,
    steepest_descent,
)


PROJECT = Path(__file__).resolve().parent
STYLES = (
    ("#0072b2", "o", "-"),
    ("#cc5500", "s", "--"),
    ("#008564", "^", "-"),
    ("#994887", "D", "--"),
    ("#765234", "v", "-."),
    ("#4254a0", "P", "-"),
    ("#b22751", "X", "--"),
)


@dataclass
class Result:
    name: str
    x: np.ndarray | None
    status: str
    residuals: list[float] = field(default_factory=list)


def default_system():
    """Практикум, II.10.5, вариант «м»."""
    n = 20
    a = 10.0 * np.eye(n)
    for offset, value in ((1, 1.0), (2, 0.1)):
        band = np.diag(np.full(n - offset, value), k=offset)
        a += band + band.T
    return a, np.arange(1, n + 1, dtype=float)


def load_system(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "A" not in data or "b" not in data:
        raise ValueError('ожидается объект JSON с ключами "A" и "b"')
    a = np.asarray(data["A"], dtype=float)
    b = np.asarray(data["b"], dtype=float)
    if a.ndim != 2 or a.shape[0] == 0 or a.shape[0] != a.shape[1]:
        raise ValueError("матрица A должна быть непустой и квадратной")
    if b.shape != (len(a),):
        raise ValueError("b должен быть одномерным вектором длины, равной порядку A")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("коэффициенты системы должны быть конечными числами")
    return a, b


def is_positive_definite(a):
    if not np.array_equal(a, a.T):
        return False
    try:
        np.linalg.cholesky(a)
    except np.linalg.LinAlgError:
        return False
    return True


def residual_norm(a, b, x):
    return float(np.linalg.norm(b - a @ x))


def run_direct(name, method, a, b):
    try:
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            x = method(a, b)
            norm = residual_norm(a, b, x)
        if not math.isfinite(norm):
            raise ArithmeticError("норма невязки не является конечной")
    except ArithmeticError as exc:
        return Result(name, None, f"сбой: {exc}")
    return Result(name, x, "решено")


def run_iterative(name, steps, a, b, x0, target, max_iterations):
    x = x0
    history = [residual_norm(a, b, x)]
    if history[0] <= target:
        return Result(name, x, "точность достигнута", history)

    status = "достигнут предел итераций"
    for _ in range(max_iterations):
        try:
            with np.errstate(over="raise", divide="raise", invalid="raise"):
                candidate = next(steps)
                norm = residual_norm(a, b, candidate)
            if not math.isfinite(norm):
                raise ArithmeticError("норма невязки не является конечной")
        except ArithmeticError as exc:
            status = f"сбой: {exc}"
            break

        history.append(norm)
        if norm <= target:
            return Result(name, candidate, "точность достигнута", history)
        if np.array_equal(x, candidate):
            status = "итерации перестали менять решение"
            break
        x = candidate

    return Result(name, x, status, history)


def solve(a, b, tolerance, max_iterations, omega):
    x0 = np.zeros_like(b)
    scale = float(np.linalg.norm(b)) or 1.0
    if not math.isfinite(scale):
        raise ValueError("норма b превышает числовой диапазон")
    target = tolerance * scale
    spd = is_positive_definite(a)

    direct = [
        run_direct("Гаусс с выбором элемента", gaussian_elimination, a, b),
        run_direct("LU-разложение", lu_solve, a, b),
    ]
    iterative_methods = (
        ("Якоби", jacobi(a, b, x0), False),
        ("Гаусс–Зейдель", relaxation(a, b, x0, 1.0), False),
        ("Верхняя релаксация", relaxation(a, b, x0, omega), False),
        ("Градиентный спуск", steepest_descent(a, b, x0), True),
        ("Минимальные невязки", minimum_residual(a, b, x0), False),
        ("Сопряжённые градиенты", conjugate_gradient(a, b, x0), True),
        ("BiCGStab", bicgstab(a, b, x0, target), False),
    )
    iterative = []
    for name, steps, requires_spd in iterative_methods:
        if requires_spd and not spd:
            iterative.append(Result(name, None, "требуется симметричная положительно определённая матрица"))
        else:
            iterative.append(run_iterative(name, steps, a, b, x0, target, max_iterations))
    return direct, iterative, scale


def print_results(a, b, direct, iterative, scale):
    print(f"{'Метод':28} {'Итерации':>9} {'||b − Ax||₂':>13} {'||b − Ax||₂ / s':>17}  Результат")
    for result in direct + iterative:
        iterations = str(len(result.residuals) - 1) if result.residuals else "—"
        absolute = relative = "—"
        if result.x is not None:
            norm = residual_norm(a, b, result.x)
            absolute, relative = f"{norm:.4e}", f"{norm / scale:.4e}"
        print(f"{result.name:28} {iterations:>9} {absolute:>13} {relative:>17}  {result.status}")

    solution = next((result for result in direct + iterative
                     if result.status in ("решено", "точность достигнута")), None)
    if solution is not None:
        print(f"\nВектор решения ({solution.name})")
        print(np.array2string(solution.x, precision=10, max_line_width=90, threshold=np.inf))


def plot_convergence(results, scale, tolerance, omega, zero_rhs, title, output, show):
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    fig, ax = plt.subplots(figsize=(10.2, 5.0), layout="constrained")
    fig.suptitle("Сходимость итерационных методов", fontsize=17, fontweight="semibold")
    ax.set_title(title, fontsize=11, color="#46566a", pad=10)
    for result, (color, marker, line) in zip(results, STYLES):
        if not result.residuals:
            continue
        residuals = np.asarray(result.residuals) / scale
        residuals[residuals <= 0] = np.nan
        label = result.name
        if label == "Верхняя релаксация":
            label += rf" ($\omega={omega:g}$)"
        ax.semilogy(residuals, color=color, linestyle=line, marker=marker,
                    markersize=5, markerfacecolor="white", linewidth=1.6, label=label)

    ax.axhline(tolerance, color="#606b78", linestyle=":", linewidth=1.2,
               label="Порог остановки")
    ylabel = r"Норма невязки $\|b-Ax^{(k)}\|_2$"
    if not zero_rhs:
        ylabel = r"Относительная невязка $\|b-Ax^{(k)}\|_2/\|b\|_2$"
    ax.set(xlabel="Номер итерации k", ylabel=ylabel)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlim(left=-0.3)
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#d5dce5", linewidth=0.75)
    ax.grid(which="minor", axis="y", color="#eef1f5", linewidth=0.5)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=9)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    if show:
        plt.show()
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Сравнение методов решения квадратной СЛАУ")
    parser.add_argument("--system", type=Path, help="путь к JSON-файлу с матрицей A и вектором b")
    parser.add_argument("--tol", type=float, default=1e-10, help="порог остановки")
    parser.add_argument("--max-iterations", type=int, default=2000, help="предел числа итераций")
    parser.add_argument("--omega", type=float, default=1.05, help="коэффициент верхней релаксации")
    parser.add_argument("--output", type=Path, help="путь к итоговому графику PNG")
    parser.add_argument("--show", action="store_true", help="открыть график в отдельном окне")
    args = parser.parse_args()

    if not 0 < args.tol < 1 or args.max_iterations < 1 or not 1 < args.omega < 2:
        parser.error("требуются 0 < tol < 1, max-iterations ≥ 1 и 1 < omega < 2")
    output = args.output or PROJECT / ("convergence-custom.png" if args.system else "convergence.png")
    if output.suffix.lower() != ".png":
        parser.error("для --output требуется расширение .png")
    try:
        a, b = load_system(args.system) if args.system else default_system()
        direct, iterative, scale = solve(a, b, args.tol, args.max_iterations, args.omega)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        parser.error(str(exc))

    title = f"Пользовательская система · n = {len(b)}" if args.system else "II.10.5 · вариант «м» · n = 20"
    print(title)
    print(f"s = {scale:.6e}    ε = {args.tol:.0e}    ω = {args.omega:g}\n")
    print_results(a, b, direct, iterative, scale)
    plot_convergence(iterative, scale, args.tol, args.omega, not np.any(b), title, output, args.show)


if __name__ == "__main__":
    main()
