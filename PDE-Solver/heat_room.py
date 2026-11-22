"""Стационарное поле температуры в комнате 4 × 3 × 2,6 м.

Задача Дирихле для уравнения Лапласа ΔT = 0 в параллелепипеде
[0, Lx] × [0, Ly] × [0, Lz]. Пол и стены держат 20 °C, на потолке задан
рисунок из двух гауссовых пятен и волнового узора.

Схема — семиточечный «крест» с шагами hx, hy, hz (Лобанов, Петров,
лекция 14). Сеточная система решается итерационно: Якоби, Зейдель и
верхняя релаксация (SOR). Зейдель и SOR обходят узлы в лексикографическом
порядке, как в учебнике; для скорости узлы одной диагональной плоскости
i + j + k = const обновляются одной векторной операцией — соседи таких узлов
лежат на соседних плоскостях, поэтому результат совпадает с поточечным
обходом.
"""

from dataclasses import dataclass, field, replace
from math import cos, pi, sqrt
import time

import numpy as np

LX, LY, LZ = 4.0, 3.0, 2.6
T_WALL = 20.0
SPOT_WEIGHTS = (0.65, 0.30)
BASE_LEVEL, WAVE_WEIGHT = 0.12, 0.15


@dataclass(frozen=True)
class Spot:
    """Гауссово пятно на потолке в нормированных координатах u = x/Lx, v = y/Ly."""

    u: float
    v: float
    sx: float
    sy: float


@dataclass(frozen=True)
class Ceiling:
    amplitude: float = 60.0
    m: int = 2
    n: int = 2
    spots: tuple = (Spot(0.33, 0.55, 0.16, 0.22), Spot(0.72, 0.35, 0.13, 0.17))
    # Множители слагаемых формулы; нужны, чтобы по линейности разложить поле.
    base: float = BASE_LEVEL
    weights: tuple = SPOT_WEIGHTS
    wave: float = WAVE_WEIGHT

    def only(self, part):
        """Потолок, на котором оставлено одно слагаемое формулы."""
        zero = dict(base=0.0, weights=(0.0, 0.0), wave=0.0)
        keep = {
            "base": dict(base=self.base),
            "spot1": dict(weights=(self.weights[0], 0.0)),
            "spot2": dict(weights=(0.0, self.weights[1])),
            "wave": dict(wave=self.wave),
        }[part]
        return replace(self, **{**zero, **keep})


DEFAULT_CEILING = Ceiling()


def ceiling_temperature(x, y, ceiling=DEFAULT_CEILING):
    u = np.asarray(x, dtype=float) / LX
    v = np.asarray(y, dtype=float) / LY
    gauss = [np.exp(-0.5 * (((u - s.u) / s.sx) ** 2 + ((v - s.v) / s.sy) ** 2))
             for s in ceiling.spots]
    # Сдвиги волн и пятен не нужны: синусы и косинусы берём как в формуле.
    wave = 0.5 * (1.0 + np.sin(2 * pi * ceiling.m * u) * np.cos(2 * pi * ceiling.n * v))
    envelope = np.sin(pi * u) ** 2 * np.sin(pi * v) ** 2
    pattern = (ceiling.base + ceiling.weights[0] * gauss[0]
               + ceiling.weights[1] * gauss[1] + ceiling.wave * wave)
    return T_WALL + ceiling.amplitude * envelope * pattern


@dataclass(frozen=True)
class Grid:
    """Равномерная сетка: nx, ny, nz — число шагов по осям."""

    nx: int
    ny: int
    nz: int

    @classmethod
    def with_step(cls, h):
        return cls(round(LX / h), round(LY / h), round(LZ / h))

    @property
    def steps(self):
        return LX / self.nx, LY / self.ny, LZ / self.nz

    @property
    def axes(self):
        return (np.linspace(0, LX, self.nx + 1), np.linspace(0, LY, self.ny + 1),
                np.linspace(0, LZ, self.nz + 1))

    @property
    def shape(self):
        return self.nx + 1, self.ny + 1, self.nz + 1

    @property
    def unknowns(self):
        return (self.nx - 1) * (self.ny - 1) * (self.nz - 1)

    @property
    def coefficients(self):
        hx, hy, hz = self.steps
        return 1 / hx**2, 1 / hy**2, 1 / hz**2

    def jacobi_radius(self):
        """Спектральный радиус матрицы перехода метода Якоби."""
        cx, cy, cz = self.coefficients
        return ((cx * cos(pi / self.nx) + cy * cos(pi / self.ny) + cz * cos(pi / self.nz))
                / (cx + cy + cz))

    def optimal_omega(self):
        """Оптимальный параметр SOR по теореме Янга: ω = 2 / (1 + √(1 − ρ²))."""
        rho = self.jacobi_radius()
        return 2 / (1 + sqrt(1 - rho**2))


def boundary_field(grid, ceiling=DEFAULT_CEILING, interior=T_WALL):
    """Сеточная функция с граничными значениями; внутри — начальное приближение."""
    x, y, _ = grid.axes
    T = np.full(grid.shape, float(interior))
    T[0, :, :] = T[-1, :, :] = T[:, 0, :] = T[:, -1, :] = T[:, :, 0] = T_WALL
    T[:, :, -1] = ceiling_temperature(x[:, None], y[None, :], ceiling)
    return T


def laplacian(T, grid):
    """Семиточечный разностный оператор Λ = Λx + Λy + Λz во внутренних узлах."""
    cx, cy, cz = grid.coefficients
    c = T[1:-1, 1:-1, 1:-1]
    return (cx * (T[:-2, 1:-1, 1:-1] + T[2:, 1:-1, 1:-1])
            + cy * (T[1:-1, :-2, 1:-1] + T[1:-1, 2:, 1:-1])
            + cz * (T[1:-1, 1:-1, :-2] + T[1:-1, 1:-1, 2:])
            - 2 * (cx + cy + cz) * c)


def rhs_norm(T, grid):
    """‖b‖∞ для системы относительно θ = T − 20: вклад граничных значений."""
    start = T.copy()
    start[1:-1, 1:-1, 1:-1] = T_WALL
    return max(1.0, float(np.abs(laplacian(start, grid)).max()))


def relative_residual(T, grid, norm_b):
    return float(np.abs(laplacian(T, grid)).max()) / norm_b


class _Wavefront:
    """Индексы внутренних узлов, сгруппированные по плоскостям i + j + k = s."""

    def __init__(self, grid):
        nx, ny, nz = grid.shape
        self.strides = (ny * nz, nz, 1)
        i, j, k = np.meshgrid(np.arange(1, nx - 1), np.arange(1, ny - 1),
                              np.arange(1, nz - 1), indexing="ij")
        s = (i + j + k).ravel()
        flat = np.ravel_multi_index((i.ravel(), j.ravel(), k.ravel()), (nx, ny, nz))
        order = np.argsort(s, kind="stable")
        s, flat = s[order], flat[order]
        cuts = np.flatnonzero(np.diff(s)) + 1
        self.planes = np.split(flat, cuts)


_WAVEFRONTS = {}


def _wavefront(grid):
    if grid not in _WAVEFRONTS:
        _WAVEFRONTS[grid] = _Wavefront(grid)
    return _WAVEFRONTS[grid]


def jacobi_sweep(T, grid):
    cx, cy, cz = grid.coefficients
    T[1:-1, 1:-1, 1:-1] = (cx * (T[:-2, 1:-1, 1:-1] + T[2:, 1:-1, 1:-1])
                           + cy * (T[1:-1, :-2, 1:-1] + T[1:-1, 2:, 1:-1])
                           + cz * (T[1:-1, 1:-1, :-2] + T[1:-1, 1:-1, 2:])
                           ) / (2 * (cx + cy + cz))


def relaxation_sweep(T, grid, omega):
    """Одна итерация верхней релаксации (П2.38); при omega = 1 — метод Зейделя (П2.37)."""
    cx, cy, cz = grid.coefficients
    inv_diag = 1 / (2 * (cx + cy + cz))
    front = _wavefront(grid)
    si, sj, sk = front.strides
    flat = T.reshape(-1)
    for idx in front.planes:
        seidel = (cx * (flat[idx - si] + flat[idx + si])
                  + cy * (flat[idx - sj] + flat[idx + sj])
                  + cz * (flat[idx - sk] + flat[idx + sk])) * inv_diag
        if omega == 1.0:
            flat[idx] = seidel
        else:
            flat[idx] += omega * (seidel - flat[idx])


@dataclass
class Solution:
    method: str
    grid: Grid
    T: np.ndarray
    iterations: int
    residuals: list = field(default_factory=list)
    seconds: float = 0.0
    omega: float = 1.0

    @property
    def residual(self):
        return self.residuals[-1]


def solve(grid, ceiling=DEFAULT_CEILING, method="sor", tol=1e-8, omega=None,
          start=None, max_iterations=200_000):
    """Решает сеточную задачу до ‖b − Av‖∞ / max(1, ‖b‖∞) ≤ tol.

    method: "jacobi", "seidel" или "sor"; start — начальное приближение
    (например, поле прошлого расчёта); граничные значения всегда берутся новые.
    """
    T = boundary_field(grid, ceiling)
    if start is not None:
        T[1:-1, 1:-1, 1:-1] = start[1:-1, 1:-1, 1:-1]
    if method == "sor":
        omega = grid.optimal_omega() if omega is None else float(omega)
    elif method == "seidel":
        omega = 1.0
    elif method != "jacobi":
        raise ValueError(f"неизвестный метод: {method}")

    norm_b = rhs_norm(T, grid)
    residuals = [relative_residual(T, grid, norm_b)]
    began = time.perf_counter()
    iterations = 0
    while residuals[-1] > tol:
        if iterations >= max_iterations:
            raise RuntimeError(f"{method}: нет сходимости за {max_iterations} итераций")
        if method == "jacobi":
            jacobi_sweep(T, grid)
        else:
            relaxation_sweep(T, grid, omega)
        iterations += 1
        residuals.append(relative_residual(T, grid, norm_b))
        if not np.isfinite(residuals[-1]):
            raise ArithmeticError(f"{method}: итерации расходятся")
    return Solution(method, grid, T, iterations, residuals,
                    time.perf_counter() - began, omega or 1.0)


def predicted_iterations(grid, method, tol):
    """Оценка числа итераций ln(1/tol) / ln(1/ρ) по спектральному радиусу."""
    rho = grid.jacobi_radius()
    rho = {"jacobi": rho, "seidel": rho**2, "sor": grid.optimal_omega() - 1}[method]
    return np.log(1 / tol) / -np.log(rho)


# --- Проверки: точное решение методом Фурье -------------------------------

def _products(a, b, c):
    """a @ b @ c. Accelerate (BLAS в numpy для macOS) иногда поднимает ложные флаги
    переполнения в matmul при верном результате — их предупреждения здесь не нужны."""
    with np.errstate(all="ignore"):
        result = a @ b @ c
    if not np.isfinite(result).all():
        raise ArithmeticError("переполнение при разложении по синусам")
    return result


def _sine_matrix(n, points):
    p = np.arange(1, n)[:, None]
    return np.sin(pi * p * points[None, :])


def _sinh_ratio(mu, steps):
    """sinh(mu·k) / sinh(mu·n) для k = steps / n без переполнения."""
    mu, steps = np.asarray(mu)[..., None], np.asarray(steps)[None, :]
    total = steps[..., -1:]
    return np.exp(mu * (steps - total)) * (-np.expm1(-2 * mu * steps)) / (-np.expm1(-2 * mu * total))


def discrete_exact(grid, ceiling=DEFAULT_CEILING):
    """Точное решение сеточной системы через собственные функции sin(pπi/N)·sin(qπj/M).

    По z для каждой гармоники остаётся разностное уравнение второго порядка,
    его решение — sinh(μk)/sinh(μN), cosh μ = 1 + λ_pq·hz²/2.
    """
    x, y, _ = grid.axes
    cx, cy, cz = grid.coefficients
    theta = ceiling_temperature(x[1:-1, None], y[None, 1:-1], ceiling) - T_WALL
    sx = _sine_matrix(grid.nx, np.arange(1, grid.nx) / grid.nx)
    sy = _sine_matrix(grid.ny, np.arange(1, grid.ny) / grid.ny)
    coef = (2 / grid.nx) * (2 / grid.ny) * _products(sx, theta, sy.T)
    p = np.arange(1, grid.nx)[:, None]
    q = np.arange(1, grid.ny)[None, :]
    lam = 4 * cx * np.sin(pi * p / (2 * grid.nx)) ** 2 + 4 * cy * np.sin(pi * q / (2 * grid.ny)) ** 2
    mu = np.arccosh(1 + lam / (2 * cz))
    ratio = _sinh_ratio(mu.ravel(), np.arange(grid.nz + 1)).reshape(*mu.shape, grid.nz + 1)
    inner = np.einsum("pi,pqk,qj->ijk", sx, coef[..., None] * ratio, sy)
    T = boundary_field(grid, ceiling)
    T[1:-1, 1:-1, 1:-1] = T_WALL + inner[:, :, 1:-1]
    return T


def continuous_exact(grid, ceiling=DEFAULT_CEILING, modes=96, quadrature=1536):
    """Решение дифференциальной задачи рядом Фурье в узлах сетки:
    θ = Σ a_pq sin(pπx/Lx) sin(qπy/Ly) sinh(k_pq z) / sinh(k_pq Lz).
    """
    n = quadrature
    u = np.arange(1, n) / n
    theta = ceiling_temperature(u[:, None] * LX, u[None, :] * LY, ceiling) - T_WALL
    s = _sine_matrix(n, u)[:modes]
    coef = (2 / n) ** 2 * _products(s, theta, s.T)
    p = np.arange(1, modes + 1)[:, None]
    q = np.arange(1, modes + 1)[None, :]
    k = pi * np.sqrt((p / LX) ** 2 + (q / LY) ** 2)
    x, y, z = grid.axes
    ratio = _sinh_ratio(k.ravel() * LZ / grid.nz, np.arange(grid.nz + 1)).reshape(*k.shape, grid.nz + 1)
    bx = np.sin(pi * np.arange(1, modes + 1)[:, None] * x[None, :] / LX)
    by = np.sin(pi * np.arange(1, modes + 1)[:, None] * y[None, :] / LY)
    return T_WALL + np.einsum("pi,pqk,qj->ijk", bx, coef[..., None] * ratio, by)


def restrict(fine, coarse_grid):
    """Значения мелкой сетки в узлах вложенной вдвое более грубой."""
    return fine[::2, ::2, ::2][: coarse_grid.nx + 1, : coarse_grid.ny + 1, : coarse_grid.nz + 1]


def sample(T, grid, x, y, z):
    """Трилинейная интерполяция поля в точке (x, y, z)."""
    hx, hy, hz = grid.steps
    fx, fy, fz = x / hx, y / hy, z / hz
    i = min(int(fx), grid.nx - 1)
    j = min(int(fy), grid.ny - 1)
    k = min(int(fz), grid.nz - 1)
    tx, ty, tz = fx - i, fy - j, fz - k
    c = T[i:i + 2, j:j + 2, k:k + 2]
    c = c[0] * (1 - tx) + c[1] * tx
    c = c[0] * (1 - ty) + c[1] * ty
    return float(c[0] * (1 - tz) + c[1] * tz)
