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


def scalar_d(z):
    return np.array([np.arctan(z[0] - 1) + 2*z[0]])


def derivative_d(z):
    return np.array([[2 + 1/(1 + (z[0]-1)**2)]])


def iteration_d(z):
    return np.array([-0.5*np.arctan(z[0]-1)])


def scalar_m(z):
    return np.array([np.sqrt(z[0]+1) - 1/z[0]])


def derivative_m(z):
    return np.array([[0.5/np.sqrt(z[0]+1) + 1/z[0]**2]])


def iteration_m(z):
    return np.array([1/np.sqrt(z[0]+1)])


def system_4v(z):
    x, y = z
    return np.array([np.cos(x-1)+y-0.5, x-np.cos(y)-3])


def jacobian_4v(z):
    x, y = z
    return np.array([[-np.sin(x-1), 1], [1, np.sin(y)]])


def iteration_4v(z):
    x, y = z
    return np.array([3+np.cos(y), 0.5-np.cos(x-1)])


def system_6g(z):
    x, y = z
    return np.array([np.sin(x)-y-1.32, np.cos(y)-x+0.85])


def jacobian_6g(z):
    x, y = z
    return np.array([[np.cos(x), -1], [-1, -np.sin(y)]])


def iteration_6g(z):
    x, y = z
    return np.array([0.85+np.cos(y), np.sin(x)-1.32])


def problems():
    return (
        Problem(name="IV.12.3 д", function=scalar_d, jacobian=derivative_d,
                iteration=iteration_d, start=(0.3,), interval=(0.0, 0.6),
                reduced=lambda x: scalar_d([x])[0], restore=lambda x: np.array([x]),
                contraction=0.5),
        Problem(name="IV.12.3 м", function=scalar_m, jacobian=derivative_m,
                iteration=iteration_m, start=(0.75,), interval=(0.7, 0.8),
                reduced=lambda x: scalar_m([x])[0], restore=lambda x: np.array([x]),
                contraction=0.23),
        Problem(name="IV.12.4 в", function=system_4v, jacobian=jacobian_4v,
                iteration=iteration_4v, start=(3.5, 1.2), interval=(3.0, 4.0),
                reduced=lambda x: x-3-np.cos(0.5-np.cos(x-1)),
                restore=lambda x: np.array([x, 0.5-np.cos(x-1)]), contraction=0.998),
        Problem(name="IV.12.6 г", function=system_6g, jacobian=jacobian_6g,
                iteration=iteration_6g, start=(1.78, -0.34), interval=(1.7, 1.85),
                reduced=lambda x: x-0.85-np.cos(np.sin(x)-1.32),
                restore=lambda x: np.array([x, np.sin(x)-1.32]), contraction=0.362),
    )


def norm(vector):
    return float(np.max(np.abs(vector)))


@dataclass
class Result:
    method: str
    solution: np.ndarray
    residuals: list
    iterations: int
    interval: tuple | None = None
    stop_reason: str = "невязка и оценка приращения"


def bisection(problem, tolerance, limit):
    left, right = problem.interval
    fl, fr = problem.reduced(left), problem.reduced(right)
    if not np.isfinite([fl, fr]).all() or np.sign(fl) == np.sign(fr):
        raise ValueError("На концах интервала должны быть конечные значения разных знаков")
    history = []
    for k in range(1, limit + 1):
        middle = left + (right-left)/2
        if middle == left or middle == right:
            raise ArithmeticError(f"{problem.name}: достигнут предел точности деления")
        z = problem.restore(middle)
        residual = norm(problem.function(z))
        history.append(residual)
        if residual <= tolerance and (right-left)/2 <= tolerance:
            return Result("Половинное деление", z, history, k, (left, right),
                          "невязка и половина длины интервала")
        fm = problem.reduced(middle)
        if not np.isfinite(fm) or not np.isfinite(residual):
            raise ArithmeticError(f"{problem.name}: неконечная невязка")
        # Нулевое машинное значение остаётся правым концом интервала.
        # Проверка длины и исходной невязки выполняется на каждом шаге.
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
            if result.residuals[-1] == 0:
                last = first + len(values) - 1
                ax.annotate(f"k={last}, r=0\nмашинный ноль", xy=(last, 0.02),
                            xycoords=("data", "axes fraction"), xytext=(18, 16),
                            textcoords="offset points", fontsize=8, color=color,
                            arrowprops=dict(arrowstyle="->", color=color))
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
        control = bisection(problem, 1e-13, 2000)
        print(f"Контрольный интервал {control.interval}, "
              f"полудлина {(control.interval[1]-control.interval[0])/2:.3e}")
        for result in results:
            coordinates = ", ".join(f"{v:.12f}" for v in result.solution)
            print(f"{result.method:25}  ({coordinates})  шагов {result.iterations:3}  "
                  f"невязка {result.residuals[-1]:.3e}  "
                  f"отклонение от контроля {norm(result.solution-control.solution):.3e}")
            print(f"  Остановка — {result.stop_reason}")
            if result.interval is not None:
                print(f"  Конечный интервал {result.interval}, "
                      f"полудлина {(result.interval[1]-result.interval[0])/2:.3e}")
    draw(experiments, Path(__file__).resolve().parent/"figures", 1e-10, args.show)


if __name__ == "__main__":
    main()
