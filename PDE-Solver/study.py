"""Численное исследование: python study.py

1. Якоби, Зейдель и SOR на одной сетке (40 × 30 × 26 шагов) при одном пороге невязки.
2. Проверка граничных условий и сеточного принципа максимума.
3. Сравнение решений на вложенных сетках h = 0,2 / 0,1 / 0,05 м и с решением рядом Фурье.
4. Затухание рисунка потолка с глубиной (по линейности — для каждого слагаемого формулы).

Пишет results.json и рисунки figures/convergence.png, figures/depth-decay.png.
"""

from dataclasses import replace
import json
from math import log, pi, sqrt
from pathlib import Path

import numpy as np

from figures import NAMES, convergence_figure, depth_figure
from heat_room import (DEFAULT_CEILING, LX, LY, LZ, T_WALL, Grid, ceiling_temperature,
                       continuous_exact, discrete_exact, predicted_iterations, restrict, solve)

HERE = Path(__file__).parent
FIGURES = HERE / "figures"
TOL = 1e-8          # порог относительной невязки при сравнении методов
TOL_FINE = 1e-10    # порог для проверок сеточной сходимости


def compare_methods(grid):
    exact = discrete_exact(grid)
    solutions, rows = [], []
    for method in ("jacobi", "seidel", "sor"):
        sol = solve(grid, method=method, tol=TOL)
        solutions.append(sol)
        rows.append({
            "method": NAMES[method],
            "omega": round(sol.omega, 4),
            "iterations": sol.iterations,
            "predicted": round(float(predicted_iterations(grid, method, TOL))),
            "seconds": round(sol.seconds, 2),
            "max_error_vs_direct": float(np.abs(sol.T - exact).max()),
        })
        print(f"  {rows[-1]['method']:8s} ω = {sol.omega:.4f}: {sol.iterations:5d} итераций "
              f"(оценка {rows[-1]['predicted']}), {sol.seconds:.2f} с, "
              f"отклонение от прямого решения {rows[-1]['max_error_vs_direct']:.1e} °C")
    return solutions, rows


def omega_scan(grid, omegas):
    result = []
    for omega in omegas:
        sol = solve(grid, method="sor", omega=omega, tol=TOL)
        result.append({"omega": omega, "iterations": sol.iterations})
        print(f"  SOR ω = {omega:.3f}: {sol.iterations} итераций")
    return result


def boundary_check(sol):
    T, grid = sol.T, sol.grid
    x, y, _ = grid.axes
    walls = np.concatenate([T[0].ravel(), T[-1].ravel(), T[:, 0].ravel(), T[:, -1].ravel(),
                            T[:, :, 0].ravel()])
    ceiling = ceiling_temperature(x[:, None], y[None, :])
    inner = T[1:-1, 1:-1, 1:-1]
    return {
        "walls_and_floor_max_dev": float(np.abs(walls - T_WALL).max()),
        "ceiling_max_dev": float(np.abs(T[:, :, -1] - ceiling).max()),
        "ceiling_edge_max_dev": float(max(np.abs(ceiling[[0, -1], :] - T_WALL).max(),
                                          np.abs(ceiling[:, [0, -1]] - T_WALL).max())),
        "interior_min": float(inner.min()),
        "interior_max": float(inner.max()),
        "ceiling_max": float(ceiling.max()),
    }


def grid_convergence(steps):
    rows, fields = [], []
    for h in steps:
        grid = Grid.with_step(h)
        sol = solve(grid, method="sor", tol=TOL_FINE)
        exact = continuous_exact(grid)
        fields.append(sol)
        rows.append({"h": h, "grid": f"{grid.nx}×{grid.ny}×{grid.nz}", "unknowns": grid.unknowns,
                     "iterations": sol.iterations, "seconds": round(sol.seconds, 2),
                     "max_error_vs_fourier": float(np.abs(sol.T - exact).max())})
    for coarse, fine, row in zip(fields, fields[1:], rows[1:]):
        row["max_diff_vs_coarser"] = float(np.abs(restrict(fine.T, coarse.grid) - coarse.T).max())
    for prev, row in zip(rows, rows[1:]):
        row["order"] = log(prev["max_error_vs_fourier"] / row["max_error_vs_fourier"]) / log(2)
    for row in rows:
        print(f"  h = {row['h']}: {row['grid']}, ошибка {row['max_error_vs_fourier']:.4f} °C"
              + (f", разность с грубой {row['max_diff_vs_coarser']:.4f} °C, порядок {row['order']:.2f}"
                 if "order" in row else ""))
    return rows


def amplitudes(theta):
    top = np.abs(theta[:, :, -1]).max()
    return np.abs(theta).max(axis=(0, 1)) / top


def depth_decay(grid):
    c = DEFAULT_CEILING
    parts = {
        "Пятно 1 (широкое)": solve(grid, c.only("spot1"), tol=TOL_FINE).T - T_WALL,
        "Пятно 2 (узкое)": solve(grid, c.only("spot2"), tol=TOL_FINE).T - T_WALL,
    }
    wave = solve(grid, c.only("wave"), tol=TOL_FINE).T
    flat = solve(grid, replace(c.only("wave"), m=0, n=0), tol=TOL_FINE).T
    parts[f"Волны m = n = {c.m}"] = wave - flat          # только осциллирующая часть R
    _, _, z = grid.axes
    depths = (LZ - z)[::-1]
    curves = [(name, amplitudes(theta)[::-1]) for name, theta in parts.items()]
    k_wave = 2 * pi * sqrt((c.m / LX) ** 2 + (c.n / LY) ** 2)
    summary = {}
    for name, values in curves:
        below = np.flatnonzero(values <= 0.1)
        half = np.flatnonzero(values <= 0.5)
        summary[name] = {"depth_50": float(depths[half[0]]), "depth_10": float(depths[below[0]])}
        print(f"  {name}: 50 % на глубине {summary[name]['depth_50']:.2f} м, "
              f"10 % — {summary[name]['depth_10']:.2f} м")
    summary["wave_k"] = k_wave
    summary["wave_depth_10_theory"] = log(10) / k_wave
    print(f"  теория для волн: k = {k_wave:.2f} 1/м, e^(-kd) = 0,1 при d = {log(10) / k_wave:.2f} м")
    return depths, curves, summary


def save(fig, name, width, height):
    FIGURES.mkdir(exist_ok=True)
    fig.write_image(FIGURES / name, width=width, height=height, scale=2)


def main():
    grid = Grid.with_step(0.1)
    print(f"Сетка {grid.nx}×{grid.ny}×{grid.nz}, неизвестных {grid.unknowns}, "
          f"ρ(Якоби) = {grid.jacobi_radius():.5f}, ω_опт = {grid.optimal_omega():.4f}")
    print("1. Сравнение методов, порог невязки", TOL)
    solutions, methods = compare_methods(grid)
    scan = omega_scan(grid, [1.5, 1.7, 1.75, 1.85, 1.9, 1.95])
    print("2. Граничные условия и принцип максимума")
    checks = boundary_check(solutions[-1])
    print("  ", checks)
    print("3. Вложенные сетки")
    grids = grid_convergence([0.2, 0.1, 0.05])
    print("4. Затухание рисунка с глубиной (сетка h = 0,05 м)")
    depths, curves, decay = depth_decay(Grid.with_step(0.05))

    save(convergence_figure(solutions, TOL), "convergence.png", 1200, 640)
    save(depth_figure(depths, curves), "depth-decay.png", 1200, 640)
    results = {
        "grid": {"nx": grid.nx, "ny": grid.ny, "nz": grid.nz, "unknowns": grid.unknowns,
                 "jacobi_radius": grid.jacobi_radius(), "optimal_omega": grid.optimal_omega()},
        "tolerance": TOL, "methods": methods, "omega_scan": scan, "checks": checks,
        "grid_convergence": grids, "depth_decay": decay,
    }
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("Готово: results.json, figures/convergence.png, figures/depth-decay.png")


if __name__ == "__main__":
    main()
