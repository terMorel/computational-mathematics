"""Численное исследование: python study.py

1. Якоби, Зейдель и SOR на сетке 40 × 30 × 26 шагов: общий старт 20 °C, общий порог невязки.
2. Граничные условия, рёбра и вершины, невязка, принцип максимума, случай A = 0.
3. Сеточная сходимость: добавка от нагрева против ряда Фурье; полное поле на вложенных сетках
   вдали от граней.
4. Горизонтальные срезы и вертикальный профиль при исходном нагреве; затухание рисунка
   потолка с глубиной по слагаемым формулы.

Пишет results.json и рисунки figures/convergence.png, figures/depth-decay.png.
"""

from dataclasses import replace
import itertools
import json
from math import log, pi, sqrt
from pathlib import Path
import platform
import statistics
import subprocess

import numpy as np

from figures import DEFAULT_VIEW, NAMES, convergence_figure, depth_figure, value_at
from heat_room import (DEFAULT_CEILING, LX, LY, LZ, T_BACKGROUND, WALLS, Grid,
                       ceiling_temperature, continuous_increment, discrete_exact, increment,
                       predicted_iterations, restrict, solve)

HERE = Path(__file__).parent
FIGURES = HERE / "figures"
TOL = 1e-8          # порог относительной невязки при сравнении методов
TOL_FINE = 1e-10    # порог для проверок сеточной сходимости и затухания
REPEATS = 3         # время — медиана трёх запусков
SLICE_HEIGHTS = [2.5, 2.2, 1.6, 1.3]   # срезы для отчёта и слайдов: глубина 0,1; 0,4; 1,0; 1,3 м


def environment():
    """Среда, в которой измерено время: система, архитектура, процессор, если известен."""
    system, machine = platform.system(), platform.machine()
    cpu = None
    try:
        if system == "Darwin":
            system = f"macOS {platform.mac_ver()[0]}"
            cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
        elif system == "Linux":
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                cpu = next((line.split(":", 1)[1].strip() for line in f if line.startswith("model name")), None)
        elif system == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            system = f"Windows {platform.release()}"
    except (OSError, subprocess.SubprocessError, ImportError):
        cpu = None
    return {"system": system, "machine": machine, "cpu": cpu or None,
            "python": platform.python_version(), "numpy": np.__version__}


def compare_methods(grid):
    exact = discrete_exact(grid)
    solutions, rows = [], []
    for method in ("jacobi", "seidel", "sor"):
        runs = [solve(grid, method=method, tol=TOL) for _ in range(REPEATS)]
        sol = runs[0]
        solutions.append(sol)
        rows.append({
            "method": NAMES[method],
            "omega": round(sol.omega, 4),
            "iterations": sol.iterations,
            "predicted": round(float(predicted_iterations(grid, method, TOL))),
            "seconds": round(statistics.median(r.seconds for r in runs), 3),
            "max_error_vs_exact": float(np.abs(sol.T - exact).max()),
        })
        print(f"  {rows[-1]['method']:8s} ω = {sol.omega:.4f}: {sol.iterations:5d} итераций "
              f"(оценка {rows[-1]['predicted']}), {rows[-1]['seconds']:.3f} с, "
              f"отличие от точного сеточного решения {rows[-1]['max_error_vs_exact']:.1e} °C")
    jac, sei, sor = rows
    gains = {
        "iterations_jacobi_to_sor": jac["iterations"] / sor["iterations"],
        "iterations_seidel_to_sor": sei["iterations"] / sor["iterations"],
        "iterations_jacobi_to_seidel": jac["iterations"] / sei["iterations"],
        "time_jacobi_to_sor": jac["seconds"] / sor["seconds"],
        "time_seidel_to_sor": sei["seconds"] / sor["seconds"],
    }
    return solutions, rows, gains


def omega_scan(grid, omegas):
    result = []
    for omega in omegas:
        sol = solve(grid, method="sor", omega=omega, tol=TOL)
        result.append({"omega": omega, "iterations": sol.iterations})
    print("  SOR:", ", ".join(f"ω = {r['omega']}: {r['iterations']}" for r in result))
    return result


def junction_rule_error(T):
    """Наибольшее отклонение рёбер и вершин от правила средних."""
    w = WALLS
    limits = {("x", 0): w.x0, ("x", 1): w.x1, ("y", 0): w.y0, ("y", 1): w.y1,
              ("z", 0): w.floor, ("z", 1): T_BACKGROUND}
    worst = 0.0
    for a, b in [("x", "y"), ("x", "z"), ("y", "z")]:
        for sa, sb in itertools.product((0, 1), repeat=2):
            index = [slice(1, -1)] * 3
            index["xyz".index(a)] = -1 if sa else 0
            index["xyz".index(b)] = -1 if sb else 0
            expected = (limits[(a, sa)] + limits[(b, sb)]) / 2
            worst = max(worst, float(np.abs(T[tuple(index)] - expected).max()))
    for s in itertools.product((0, 1), repeat=3):
        expected = (limits[("x", s[0])] + limits[("y", s[1])] + limits[("z", s[2])]) / 3
        worst = max(worst, abs(T[tuple(-1 if v else 0 for v in s)] - expected))
    return worst


def boundary_checks(sol):
    T, grid = sol.T, sol.grid
    x, y, _ = grid.axes
    w = WALLS
    faces = {
        "x = 0": float(np.abs(T[0, 1:-1, 1:-1] - w.x0).max()),
        "x = 4": float(np.abs(T[-1, 1:-1, 1:-1] - w.x1).max()),
        "y = 0": float(np.abs(T[1:-1, 0, 1:-1] - w.y0).max()),
        "y = 3": float(np.abs(T[1:-1, -1, 1:-1] - w.y1).max()),
        "пол": float(np.abs(T[1:-1, 1:-1, 0] - w.floor).max()),
        "потолок": float(np.abs(T[1:-1, 1:-1, -1]
                                - ceiling_temperature(x[1:-1, None], y[None, 1:-1])).max()),
    }
    inner = T[1:-1, 1:-1, 1:-1]
    boundary = np.concatenate([T[0].ravel(), T[-1].ravel(), T[:, 0].ravel(), T[:, -1].ravel(),
                               T[:, :, 0].ravel(), T[:, :, -1].ravel()])
    return {
        "faces_max_dev": faces,
        "junctions_max_dev": junction_rule_error(T),
        "edge_xy00": float(T[0, 0, grid.nz // 2]),
        "vertex_000": float(T[0, 0, 0]),
        "final_residual": sol.residual,
        "interior_min": float(inner.min()),
        "interior_max": float(inner.max()),
        "boundary_min": float(boundary.min()),
        "boundary_max": float(boundary.max()),
    }


def zero_amplitude(grid):
    T = solve(grid, replace(DEFAULT_CEILING, amplitude=0.0), tol=TOL).T
    inner = T[1:-1, 1:-1, 1:-1]
    result = {
        "ceiling_max_dev_from_20": float(np.abs(T[1:-1, 1:-1, -1] - T_BACKGROUND).max()),
        "walls_max_dev": max(float(np.abs(T[0, 1:-1, 1:-1] - WALLS.x0).max()),
                             float(np.abs(T[-1, 1:-1, 1:-1] - WALLS.x1).max()),
                             float(np.abs(T[1:-1, 0, 1:-1] - WALLS.y0).max()),
                             float(np.abs(T[1:-1, -1, 1:-1] - WALLS.y1).max())),
        "interior_min": float(inner.min()),
        "interior_max": float(inner.max()),
        "interior_std": float(inner.std()),
    }
    print("  A = 0:", {k: round(v, 3) for k, v in result.items()})
    return result


def increment_convergence(steps):
    """Добавка от нагрева: данные гладкие и согласованные, эталон — ряд Фурье."""
    rows, fields = [], []
    for h in steps:
        grid = Grid.with_step(h)
        theta = increment(grid, tol=TOL_FINE)
        fields.append((grid, theta))
        rows.append({"h": h, "grid": f"{grid.nx} × {grid.ny} × {grid.nz}", "unknowns": grid.unknowns,
                     "max_error": float(np.abs(theta - continuous_increment(grid)).max())})
    for (cg, coarse), (_, fine), row in zip(fields, fields[1:], rows[1:]):
        row["max_diff_vs_coarser"] = float(np.abs(restrict(fine, cg) - coarse).max())
    for prev, row in zip(rows, rows[1:]):
        row["order"] = log(prev["max_error"] / row["max_error"]) / log(2)
    for row in rows:
        print(f"  добавка h = {row['h']}: ошибка {row['max_error']:.4f} °C"
              + (f", порядок {row['order']:.2f}" if "order" in row else ""))
    return rows


def full_field_convergence(steps, margin=0.5):
    """Полное поле: скачки на стыках граней портят сходимость у рёбер, поэтому
    разности вложенных сеток меряем в max-норме только в узлах не ближе margin
    к любой грани. Эталона нет: порядок оценён по трём сеткам, log2(d1/d2)."""
    fields = []
    for h in steps:
        grid = Grid.with_step(h)
        fields.append((grid, solve(grid, tol=TOL_FINE).T))
    coarse_grid = fields[0][0]
    x, y, z = coarse_grid.axes
    inside = ((x[:, None, None] >= margin) & (x[:, None, None] <= LX - margin)
              & (y[None, :, None] >= margin) & (y[None, :, None] <= LY - margin)
              & (z[None, None, :] >= margin) & (z[None, None, :] <= LZ - margin))

    def on_coarse(grid, T):
        step = grid.nx // coarse_grid.nx
        return T[::step, ::step, ::step]

    values = [on_coarse(g, T) for g, T in fields]
    diffs = [float(np.abs(b - a)[inside].max()) for a, b in zip(values, values[1:])]
    result = {"margin_m": margin, "steps": steps, "nodes": int(inside.sum()),
              "max_diffs": diffs, "order": log(diffs[0] / diffs[1]) / log(2)}
    print(f"  полное поле вдали от граней ({margin} м): разности {diffs[0]:.4f} и {diffs[1]:.4f} °C, "
          f"порядок {result['order']:.2f}")
    return result


def slice_summary(grid, heights):
    """Пределы температуры на горизонтальных слоях при исходном нагреве.

    interior — только внутренние узлы слоя, layer — вместе с узлами на стенах;
    increment — max T(A) − T(A = 0) по внутренним узлам слоя (влияние нагрева потолка).
    """
    T = solve(grid, tol=TOL_FINE).T
    T0 = solve(grid, replace(DEFAULT_CEILING, amplitude=0.0), tol=TOL_FINE).T
    rows = []
    for z in heights:
        k = int(round(z / grid.steps[2]))
        layer, inner = T[:, :, k], T[1:-1, 1:-1, k]
        rows.append({"z": z, "depth": round(LZ - z, 6),
                     "interior_min": float(inner.min()), "interior_max": float(inner.max()),
                     "layer_min": float(layer.min()), "layer_max": float(layer.max()),
                     "increment_max": float((T - T0)[1:-1, 1:-1, k].max())})
        r = rows[-1]
        print(f"  z = {z} м: внутри {r['interior_min']:.2f}…{r['interior_max']:.2f} °C, со стенами "
              f"{r['layer_min']:.2f}…{r['layer_max']:.2f} °C, добавка до {r['increment_max']:.2f} °C")
    return rows, T, T0


def profile_summary(grid, T, T0, point, height):
    x, y = point
    result = {"x": x, "y": y, "z": height, "T": value_at(T, grid, x, y, height),
              "T_ceiling": value_at(T, grid, x, y, LZ), "T_zero_amplitude": value_at(T0, grid, x, y, height)}
    print(f"  профиль под ({x}; {y}) м: z = {height} м — {result['T']:.2f} °C, потолок {result['T_ceiling']:.2f} °C, "
          f"при A = 0 — {result['T_zero_amplitude']:.2f} °C")
    return result


def crossing(depths, values, level):
    """Глубина, на которой доля амплитуды падает до level: линейная интерполяция
    между соседними слоями сетки; возвращает и сам интервал слоёв."""
    k = int(np.flatnonzero(values <= level)[0])
    d0, d1, a0, a1 = depths[k - 1], depths[k], values[k - 1], values[k]
    return {"depth": float(d0 + (a0 - level) / (a0 - a1) * (d1 - d0)),
            "between": [float(d0), float(d1)]}


def depth_decay(grid):
    """Доля амплитуды на срезе относительно потолка для каждого слагаемого.

    Компонента — T(только это слагаемое) − T(A = 0) при тех же стенах; для волн —
    разность расчётов с m, n и с m = n = 0, то есть только осциллирующая часть R.
    Амплитуда на слое — max |компоненты| по узлам слоя; нормируем на max по
    открытой грани потолка, то есть на амплитуду этой компоненты в данных.
    """
    c = DEFAULT_CEILING
    background = solve(grid, replace(c, amplitude=0.0), tol=TOL_FINE).T

    def component(ceiling):
        return solve(grid, ceiling, tol=TOL_FINE).T - background

    wave_full = component(c.only("wave"))
    wave_flat = component(replace(c.only("wave"), m=0, n=0))
    parts = {
        "Пятно 1": component(c.only("spot1")),
        "Пятно 2": component(c.only("spot2")),
        f"Волны m = n = {c.m}": wave_full - wave_flat,
    }
    _, _, z = grid.axes
    depths = (LZ - z)[::-1]
    curves, summary = [], {}
    for name, theta in parts.items():
        top = np.abs(theta[1:-1, 1:-1, -1]).max()
        values = (np.abs(theta[1:-1, 1:-1, :]).max(axis=(0, 1)) / top)[::-1]
        curves.append((name, values))
        at = {f"{d:.1f}": float(values[int(np.argmin(np.abs(depths - d)))]) for d in (0.5, 1.0, 1.5)}
        summary[name] = {"ceiling_amplitude": float(top), "half": crossing(depths, values, 0.5),
                         "tenth": crossing(depths, values, 0.1), "fraction_at_depth": at}
        print(f"  {name}: амплитуда на потолке {top:.2f} °C, 50 % — {summary[name]['half']['depth']:.2f} м, "
              f"10 % — {summary[name]['tenth']['depth']:.2f} м (между слоями {summary[name]['tenth']['between']})")
    k_wave = 2 * pi * sqrt((c.m / LX) ** 2 + (c.n / LY) ** 2)
    summary["wave_k"] = k_wave
    summary["wave_tenth_estimate"] = log(10) / k_wave
    summary["grid"] = f"{grid.nx} × {grid.ny} × {grid.nz}"
    print(f"  оценка для гармоники k = {k_wave:.2f} 1/м: exp(−kd) = 0,1 при d = {log(10) / k_wave:.2f} м")
    return depths, curves, summary


def save(fig, name, width, height):
    FIGURES.mkdir(exist_ok=True)
    fig.write_image(FIGURES / name, width=width, height=height, scale=2)


def main():
    env = environment()   # та же среда, в которой ниже измеряется время
    print("Среда замера времени:", env)
    grid = Grid.with_step(0.1)
    print(f"Сетка {grid.nx}×{grid.ny}×{grid.nz}, неизвестных {grid.unknowns}, "
          f"ρ(Якоби) = {grid.jacobi_radius():.5f}, ω_опт = {grid.optimal_omega():.4f}")
    print("1. Методы, порог невязки", TOL)
    solutions, methods, gains = compare_methods(grid)
    print("  выигрыш:", {k: round(v, 1) for k, v in gains.items()})
    scan = omega_scan(grid, [1.5, 1.7, 1.75, 1.85, 1.9, 1.95])
    print("2. Граница и принцип максимума")
    checks = boundary_checks(solve(grid, tol=TOL_FINE))
    print("  ", checks)
    a_zero = zero_amplitude(grid)
    print("3. Сеточная сходимость")
    inc = increment_convergence([0.2, 0.1, 0.05])
    full = full_field_convergence([0.2, 0.1, 0.05])
    print("4. Срезы, профиль и затухание с глубиной")
    slices, T, T0 = slice_summary(grid, SLICE_HEIGHTS)
    profile = profile_summary(grid, T, T0, DEFAULT_VIEW["profile"], DEFAULT_VIEW["z"])
    decay_grid = Grid.with_step(0.05)
    depths, curves, decay = depth_decay(decay_grid)

    save(convergence_figure(solutions, TOL), "convergence.png", 1200, 640)
    save(depth_figure(depths, curves, decay), "depth-decay.png", 1200, 660)
    results = {
        "grid": {"nx": grid.nx, "ny": grid.ny, "nz": grid.nz, "unknowns": grid.unknowns,
                 "jacobi_radius": grid.jacobi_radius(), "optimal_omega": grid.optimal_omega()},
        "walls": {"x0": WALLS.x0, "x1": WALLS.x1, "y0": WALLS.y0, "y1": WALLS.y1, "floor": WALLS.floor},
        "tolerance": TOL,
        "timing": {"repeats": REPEATS, "statistic": "медиана", **env},
        "methods": methods, "gains": gains, "omega_scan": scan, "checks": checks,
        "zero_amplitude": a_zero, "increment_convergence": inc, "full_field_convergence": full,
        "slices": slices, "profile": profile, "depth_decay": decay,
    }
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Готово: results.json, figures/convergence.png, figures/depth-decay.png")


if __name__ == "__main__":
    main()
