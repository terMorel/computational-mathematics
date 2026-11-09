import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator


X0 = 0.5
STEPS = [2.0 / 2**n for n in range(1, 22)]
FIGURE_DIR = Path(__file__).resolve().parent / "figures"

FUNCTIONS = (
    ("sin_x_squared", r"\sin(x^2)",
     lambda x: math.sin(x**2),
     lambda x: 2 * x * math.cos(x**2)),
    ("cos_sin_x", r"\cos(\sin x)",
     lambda x: math.cos(math.sin(x)),
     lambda x: -math.sin(math.sin(x)) * math.cos(x)),
    ("exp_sin_cos_x", r"\exp(\sin(\cos x))",
     lambda x: math.exp(math.sin(math.cos(x))),
     lambda x: -math.exp(math.sin(math.cos(x))) * math.cos(math.cos(x)) * math.sin(x)),
    ("log_x_plus_3", r"\ln(x+3)",
     lambda x: math.log(x + 3),
     lambda x: 1 / (x + 3)),
    ("sqrt_x_plus_3", r"\sqrt{x+3}",
     lambda x: math.sqrt(x + 3),
     lambda x: 1 / (2 * math.sqrt(x + 3))),
)

METHOD_STYLES = (
    ("1. Правая ($p=1$)", "#0072b2", "-", "o"),
    ("2. Левая ($p=1$)", "#d55e00", "--", "x"),
    ("3. Центральная ($p=2$)", "#00835f", "-.", "^"),
    ("4. Центральная ($p=4$)", "#a44990", "-", "s"),
    ("5. Центральная ($p=6$)", "#70513a", "--", "D"),
)


def finite_differences(function, x, h):
    value = function(x)
    left = function(x - h)
    right = function(x + h)
    central_h = (right - left) / (2 * h)
    central_2h = (function(x + 2 * h) - function(x - 2 * h)) / (4 * h)
    central_3h = (function(x + 3 * h) - function(x - 3 * h)) / (6 * h)

    return (
        (right - value) / h,
        (value - left) / h,
        central_h,
        4 / 3 * central_h - 1 / 3 * central_2h,
        3 / 2 * central_h - 3 / 5 * central_2h + 1 / 10 * central_3h,
    )


def plot_errors(name, formula, function, derivative):
    exact = derivative(X0)
    estimates = [finite_differences(function, X0, h) for h in STEPS]

    fig, ax = plt.subplots(num=f"Численное дифференцирование: {name}",
                           figsize=(8.4, 5.1), layout="constrained")
    fig.suptitle(rf"$f(x)={formula}$", fontsize=17)
    ax.set_title(rf"Точка $x_0={X0:g}$ · 21 значение шага", fontsize=10, color="#46566a", pad=10)
    for (label, color, linestyle, marker), values in zip(METHOD_STYLES, zip(*estimates)):
        errors = [abs(value - exact) for value in values]
        ax.loglog(STEPS, errors, label=label, color=color, linestyle=linestyle,
                  marker=marker, markerfacecolor="none", markersize=4.5,
                  linewidth=1.5, nonpositive="mask")

    ax.set_xlabel(r"Шаг дифференцирования $h$")
    ax.set_ylabel(r"Абсолютная погрешность $|D_h f(x_0)-f'(x_0)|$")
    ax.xaxis.set_major_locator(LogLocator(numticks=9))
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#d3dae3", linewidth=0.8)
    ax.grid(which="minor", color="#eef1f5", linewidth=0.5)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncols=3,
              frameon=False, fontsize=9)
    return fig


def main():
    parser = argparse.ArgumentParser(description="Графики погрешности численного дифференцирования")
    parser.add_argument("--no-show", action="store_true", help="сохранить графики без открытия окон")
    args = parser.parse_args()

    if args.no_show:
        plt.switch_backend("Agg")

    FIGURE_DIR.mkdir(exist_ok=True)
    for name, formula, function, derivative in FUNCTIONS:
        fig = plot_errors(name, formula, function, derivative)
        fig.savefig(FIGURE_DIR / f"{name}.png", dpi=160)

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
