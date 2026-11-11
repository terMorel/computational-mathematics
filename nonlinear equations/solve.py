import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Problem:
    name: str
    function: Callable
    jacobian: Callable
    iteration: Callable
    start: tuple
    interval: tuple
    reduced: Callable
    restore: Callable
    contraction: float


def problems():
    return (
        Problem("IV.12.3 д", lambda z: np.array([np.arctan(z[0] - 1) + 2*z[0]]),
                lambda z: np.array([[2 + 1/(1 + (z[0]-1)**2)]]),
                lambda z: np.array([-0.5*np.arctan(z[0]-1)]),
                (0.3,), (0.0, 0.6), lambda x: np.arctan(x-1) + 2*x,
                lambda x: np.array([x]), 0.5),
        Problem("IV.12.3 м", lambda z: np.array([np.sqrt(z[0]+1) - 1/z[0]]),
                lambda z: np.array([[0.5/np.sqrt(z[0]+1) + 1/z[0]**2]]),
                lambda z: np.array([1/np.sqrt(z[0]+1)]),
                (0.75,), (0.7, 0.8), lambda x: np.sqrt(x+1) - 1/x,
                lambda x: np.array([x]), 0.23),
        Problem("IV.12.4 в",
                lambda z: np.array([np.cos(z[0]-1)+z[1]-0.5, z[0]-np.cos(z[1])-3]),
                lambda z: np.array([[-np.sin(z[0]-1), 1], [1, np.sin(z[1])]]),
                lambda z: np.array([3+np.cos(z[1]), 0.5-np.cos(z[0]-1)]),
                (3.5, 1.2), (3.0, 4.0),
                lambda x: x-3-np.cos(0.5-np.cos(x-1)),
                lambda x: np.array([x, 0.5-np.cos(x-1)]), 0.998),
        Problem("IV.12.6 г",
                lambda z: np.array([np.sin(z[0])-z[1]-1.32, np.cos(z[1])-z[0]+0.85]),
                lambda z: np.array([[np.cos(z[0]), -1], [-1, -np.sin(z[1])]]),
                lambda z: np.array([0.85+np.cos(z[1]), np.sin(z[0])-1.32]),
                (1.78, -0.34), (1.7, 1.85),
                lambda x: x-0.85-np.cos(np.sin(x)-1.32),
                lambda x: np.array([x, np.sin(x)-1.32]), 0.362),
    )


def norm(vector):
    return float(np.max(np.abs(vector)))


@dataclass
class Result:
    method: str
    solution: np.ndarray
    residuals: list
    iterations: int


def bisection(problem, tolerance, limit):
    left, right = problem.interval
    fl, fr = problem.reduced(left), problem.reduced(right)
    if not np.isfinite([fl, fr]).all() or np.sign(fl) == np.sign(fr):
        raise ValueError("На концах интервала должны быть конечные значения разных знаков")
    history = []
    for k in range(1, limit + 1):
        middle = left + (right-left)/2
        z = problem.restore(middle)
        residual = norm(problem.function(z))
        history.append(residual)
        if residual <= tolerance and (right-left)/2 <= tolerance:
            return Result("Половинное деление", z, history, k)
        fm = problem.reduced(middle)
        if fm == 0:
            return Result("Половинное деление", z, history, k)
        if np.sign(fm) == np.sign(fl):
            left, fl = middle, fm
        else:
            right = middle
    raise RuntimeError(f"{problem.name}: превышен предел делений")


def iterate(problem, method, tolerance, limit):
    z = np.array(problem.start, dtype=float)
    history = [norm(problem.function(z))]
    fixed_jacobian = problem.jacobian(z)
    for k in range(1, limit + 1):
        if method == "Простая итерация":
            updated = problem.iteration(z)
            error = problem.contraction/(1-problem.contraction) * norm(updated-z)
        else:
            jacobian = fixed_jacobian if method == "Модифицированный Ньютон" else problem.jacobian(z)
            updated = z - np.linalg.solve(jacobian, problem.function(z))
            error = norm(updated-z)
        residual = norm(problem.function(updated))
        if not np.isfinite(updated).all() or not np.isfinite(residual):
            raise ArithmeticError(f"{problem.name}: итерация вышла за числовой диапазон")
        history.append(residual)
        if residual <= tolerance and error <= tolerance:
            return Result(method, updated, history, k)
        if np.array_equal(updated, z):
            raise ArithmeticError(f"{problem.name}: итерации перестали изменять приближение")
        z = updated
    raise RuntimeError(f"{problem.name}: превышен предел итераций")


def calculate(tolerance=1e-10, limit=2000):
    experiments = []
    for problem in problems():
        results = [bisection(problem, tolerance, limit)]
        results.extend(iterate(problem, method, tolerance, limit) for method in
                       ("Простая итерация", "Ньютон", "Модифицированный Ньютон"))
        experiments.append((problem, results))
    return experiments


def draw(experiments, directory, tolerance, show):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    directory.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4), layout="constrained")
    for ax, (problem, results) in zip(axes.flat, experiments):
        for result, color, marker in zip(results,
                                         ("#0072b2", "#008564", "#cc5500", "#994887"),
                                         ("o", "^", "s", "D")):
            values = np.array(result.residuals)
            values[values == 0] = np.nan
            first = 1 if result.method == "Половинное деление" else 0
            ax.semilogy(np.arange(first, first+len(values)), values, label=result.method,
                        color=color, marker=marker, markersize=3, linewidth=1.3)
        ax.axhline(tolerance, color="gray", linestyle=":", linewidth=1)
        ax.set(title=problem.name, xlabel="Число шагов k", ylabel=r"$\|F(z_k)\|_\infty$")
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Сходимость методов решения нелинейных задач", fontsize=16)
    fig.savefig(directory/"convergence.png", dpi=150)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4), layout="constrained")
    for ax, (problem, results) in zip(axes.flat[:2], experiments[:2]):
        x = np.linspace(*problem.interval, 400)
        ax.plot(x, [problem.reduced(t) for t in x], color="#0072b2")
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.scatter(results[2].solution[0], 0, color="#cc5500", zorder=3)
        ax.set(title=problem.name, xlabel="x", ylabel="f(x)")
        ax.grid(alpha=0.25)
    bounds = ((2, 4.2, -0.6, 1.6), (-0.2, 2, -1.6, 0))
    for ax, (problem, results), (xl, xr, yl, yr) in zip(axes.flat[2:], experiments[2:], bounds):
        xx, yy = np.meshgrid(np.linspace(xl, xr, 400), np.linspace(yl, yr, 400))
        values = problem.function(np.array([xx, yy]))
        ax.contour(xx, yy, values[0], levels=[0], colors=["#0072b2"])
        ax.contour(xx, yy, values[1], levels=[0], colors=["#008564"])
        ax.plot([], [], color="#0072b2", label=r"$F_1=0$")
        ax.plot([], [], color="#008564", label=r"$F_2=0$")
        ax.scatter(*results[2].solution, color="#cc5500", zorder=3, label="Решение")
        ax.set(title=problem.name, xlabel="x", ylabel="y")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)
    fig.suptitle("Отделение корней и пересечение кривых", fontsize=16)
    fig.savefig(directory/"geometry.png", dpi=150)
    if show:
        plt.show()
    plt.close("all")


def main():
    parser = argparse.ArgumentParser(description="Лабораторная работа 3. Нелинейные уравнения")
    parser.add_argument("--show", action="store_true", help="открыть графики в окнах")
    args = parser.parse_args()
    experiments = calculate()
    for problem, results in experiments:
        print(f"\n{problem.name}")
        for result in results:
            coordinates = ", ".join(f"{v:.12f}" for v in result.solution)
            print(f"{result.method:25}  ({coordinates})  шагов {result.iterations:3}  "
                  f"невязка {result.residuals[-1]:.3e}")
    draw(experiments, Path(__file__).resolve().parent/"figures", 1e-10, args.show)


if __name__ == "__main__":
    main()
