"""Стационарное поле температуры в комнате [0, 4] × [0, 3] × [0, 2,6] м.

Задача Дирихле для уравнения Лапласа ΔT = 0 (однородная среда, постоянная
теплопроводность, без источников). Пять граней держат постоянные температуры,
на потолке — формула с двумя гауссовыми пятнами и волнами на фоне 20 °C.

Схема — семиточечный «крест» с шагами hx, hy, hz. Сеточная система решается
методами Якоби, Зейделя и верхней релаксации (SOR).
"""

from dataclasses import dataclass, field, replace
from math import cos, pi, sin, sqrt
import time

import numpy as np

# --- Данные задачи -----------------------------------------------------------
# Размеры комнаты, фон потолка 20 °C и веса слагаемых формулы потолка. Ниже —
# температуры стен и пола (Walls), параметры одного пятна (Spot) и весь нагрев
# потолка (Ceiling): сила A, волновые числа m, n, два пятна и веса слагаемых.

LX, LY, LZ = 4.0, 3.0, 2.6
T_BACKGROUND = 20.0
SPOT_WEIGHTS = (0.65, 0.30)
BASE_LEVEL, WAVE_WEIGHT = 0.12, 0.15


@dataclass(frozen=True)
class Walls:
    """Постоянные температуры открытых граней, °C."""

    x0: float = 16.0
    x1: float = 24.0
    y0: float = 18.0
    y1: float = 22.0
    floor: float = 20.0

    @property
    def coldest(self):
        return min(self.x0, self.x1, self.y0, self.y1, self.floor, T_BACKGROUND)

    @property
    def warmest(self):
        return max(self.x0, self.x1, self.y0, self.y1, self.floor, T_BACKGROUND)


WALLS = Walls()


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


# --- Температура потолка φ₆(x, y) --------------------------------------------
# φ₆ = 20 + A · sin²πu · sin²πv · (0,12 + 0,65·G₁ + 0,30·G₂ + 0,15·R), u = x/Lx, v = y/Ly.
# «Колпак» sin²πu · sin²πv обнуляет нагрев на краю потолка; G₁, G₂ — гауссовы
# пятна, R — волновой узор. Считается сразу для целого массива точек.

def ceiling_temperature(x, y, ceiling=DEFAULT_CEILING):
    u = np.asarray(x, dtype=float) / LX
    v = np.asarray(y, dtype=float) / LY
    gauss = [np.exp(-0.5 * (((u - s.u) / s.sx) ** 2 + ((v - s.v) / s.sy) ** 2))
             for s in ceiling.spots]
    wave = 0.5 * (1.0 + np.sin(2 * pi * ceiling.m * u) * np.cos(2 * pi * ceiling.n * v))
    envelope = np.sin(pi * u) ** 2 * np.sin(pi * v) ** 2
    pattern = (ceiling.base + ceiling.weights[0] * gauss[0]
               + ceiling.weights[1] * gauss[1] + ceiling.wave * wave)
    return T_BACKGROUND + ceiling.amplitude * envelope * pattern


# --- Сетка -------------------------------------------------------------------
# Равномерная сетка с шагом h: размер массива узлов, число неизвестных и
# коэффициенты 1/h² для шаблона «крест». Здесь же теория сходимости: границы
# спектра оператора, спектральный радиус метода Якоби и оптимальный параметр
# верхней релаксации τ (в коде — omega).

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

    def spectrum_bounds(self):
        """Границы спектра оператора A = −Λ на сетке с нулевыми граничными условиями:
        λ_pqr = Σ (4/h²) sin²(pπ/2M) по осям; l = λ_111, L = λ_{M−1,M−1,M−1}."""
        parts = [(4 / h**2, pi / (2 * n)) for h, n in zip(self.steps, (self.nx, self.ny, self.nz))]
        low = sum(c * sin(a) ** 2 for c, a in parts)
        high = sum(c * cos(a) ** 2 for c, a in parts)
        return low, high

    def jacobi_radius(self):
        """Спектральный радиус матрицы перехода метода Якоби."""
        cx, cy, cz = self.coefficients
        return ((cx * cos(pi / self.nx) + cy * cos(pi / self.ny) + cz * cos(pi / self.nz))
                / (cx + cy + cz))

    def optimal_omega(self):
        """Оптимальный параметр SOR (теорема Янга): ω = 2 / (1 + √(1 − ρ²))."""
        rho = self.jacobi_radius()
        return 2 / (1 + sqrt(1 - rho**2))


# --- Граничные условия -------------------------------------------------------
# Заполняем граничные узлы массива T: на каждой грани — её температура, на рёбрах
# и в вершинах — среднее пределов соседних граней, внутри — начальное приближение.
# junctions собирает ту же таблицу стыков для подсказок в 3D-сцене стенда.

FACES =(("стена x = 0", "x = 0"), ("стена x = 4 м", "x = 4"), ("стена y = 0", "y = 0"),
         ("стена y = 3 м", "y = 3"), ("пол z = 0", "z = 0"), ("потолок z = 2,6 м", "z = 2,6"))


def _faces(grid, ceiling, walls):
    """Для каждой грани: маска узлов, значение на открытой грани, предел на её краю."""
    nx, ny, nz = grid.shape
    x, y, _ = grid.axes
    i = np.arange(nx)[:, None, None]
    j = np.arange(ny)[None, :, None]
    k = np.arange(nz)[None, None, :]
    return [
        (i == 0, walls.x0, walls.x0),
        (i == nx - 1, walls.x1, walls.x1),
        (j == 0, walls.y0, walls.y0),
        (j == ny - 1, walls.y1, walls.y1),
        (k == 0, walls.floor, walls.floor),
        (k == nz - 1, ceiling_temperature(x[:, None, None], y[None, :, None], ceiling), T_BACKGROUND),
    ]


def boundary_field(grid, ceiling=DEFAULT_CEILING, walls=WALLS, interior=T_BACKGROUND):
    """Сеточная функция с граничными значениями; внутри — начальное приближение.

    Соглашение на стыках. Узел, лежащий только на одной грани, получает значение
    этой грани (на потолке — по формуле). Узел на ребре получает среднее
    арифметическое предельных значений двух примыкающих граней, узел в вершине —
    среднее трёх. Предел формулы потолка на его краю равен 20 °C. Значения
    считаются по маскам граней, поэтому не зависят от порядка заполнения.

    Семиточечный шаблон внутреннего узла (i, j, k) берёт соседей, у которых
    меняется только один индекс. Сосед на границе имеет ровно один крайний
    индекс — это узел открытой грани. Узлы рёбер (два крайних индекса) и вершин
    (три) соседями внутренних узлов не бывают: на решение они не влияют
    и нужны только для изображения границы.
    """
    shape = grid.shape
    faces = _faces(grid, ceiling, walls)

    # Для каждого узла: сколько граней через него проходит и сумма их пределов.
    count = np.zeros(shape)
    limits = np.zeros(shape)
    for mask, _, edge_value in faces:
        mask = np.broadcast_to(mask, shape)
        count += mask
        limits += np.where(mask, edge_value, 0.0)

    # Внутри — начальное приближение; узлы ровно одной грани — её значение.
    T = np.full(shape, float(interior))
    for mask, value, _ in faces:
        open_face = np.broadcast_to(mask, shape) & (count == 1)
        T[open_face] = np.broadcast_to(value, shape)[open_face]

    # Рёбра (две грани) и вершины (три) — среднее пределов примыкающих граней.
    junction = count >= 2
    T[junction] = limits[junction] / count[junction]
    return T


def junctions(grid, ceiling=DEFAULT_CEILING, walls=WALLS):
    """12 рёбер и 8 вершин: узлы стыка, примыкающие грани и их пределы.

    Пределы берутся из той же таблицы граней, что и в boundary_field, поэтому
    value совпадает со значением, которое решатель хранит в этих узлах.
    """
    shape = grid.shape
    masks = [np.broadcast_to(mask, shape) for mask, _, _ in _faces(grid, ceiling, walls)]
    limits = [float(edge) for _, _, edge in _faces(grid, ceiling, walls)]
    code = sum(mask.astype(int) << f for f, mask in enumerate(masks))
    count = sum(mask.astype(int) for mask in masks)
    result = []
    for c in sorted(set(code[count >= 2].tolist()), key=lambda c: (bin(c).count("1"), c)):
        members = [f for f in range(len(FACES)) if c >> f & 1]
        result.append({
            "kind": "ребро" if len(members) == 2 else "вершина",
            "faces": [FACES[f][0] for f in members],
            "coords": [FACES[f][1] for f in members],
            "limits": [limits[f] for f in members],
            "value": sum(limits[f] for f in members) / len(members),
            "index": np.nonzero(code == c),
        })
    return result


# --- Разностный оператор и невязка -------------------------------------------
# Шаблон «крест» сразу во всех внутренних узлах через срезы массива: T[:-2] —
# соседи с меньшим индексом, T[2:] — с бо́льшим. Матрица системы не собирается:
# граничные значения лежат в том же массиве и сами попадают в правую часть.
# Относительная невязка ‖ΛT‖ / ‖b‖ — критерий остановки итераций.

def laplacian(T, grid):
    """Семиточечный разностный оператор Λ = Λx + Λy + Λz во внутренних узлах."""
    cx, cy, cz = grid.coefficients
    c = T[1:-1, 1:-1, 1:-1]
    return (cx * (T[:-2, 1:-1, 1:-1] + T[2:, 1:-1, 1:-1])
            + cy * (T[1:-1, :-2, 1:-1] + T[1:-1, 2:, 1:-1])
            + cz * (T[1:-1, 1:-1, :-2] + T[1:-1, 1:-1, 2:])
            - 2 * (cx + cy + cz) * c)


def rhs_norm(T, grid):
    """‖b‖∞ системы Av = b для внутренних узлов: вклад граничных значений."""
    boundary_only = T.copy()
    boundary_only[1:-1, 1:-1, 1:-1] = 0.0
    return max(1.0, float(np.abs(laplacian(boundary_only, grid)).max()))


def relative_residual(T, grid, norm_b):
    """‖b − Av‖∞ / max(1, ‖b‖∞); b − Av совпадает с ΛT во внутренних узлах."""
    return float(np.abs(laplacian(T, grid)).max()) / norm_b


# --- Порядок обхода для Зейделя и верхней релаксации -------------------------
# Узлы группируются по диагональным плоскостям m + l + n = s и обходятся
# плоскость за плоскостью. Результат тот же, что при обходе по одному узлу,
# но каждая плоскость считается одной операцией numpy. Плоскости строятся
# один раз для каждой сетки и хранятся в _WAVEFRONTS.

class _Wavefront:
    """Внутренние узлы, сгруппированные по плоскостям i + j + k = s.

    Лексикографический обход (как у Зейделя в учебнике) берёт новые значения
    соседей i−1, j−1, k−1 и старые — соседей i+1, j+1, k+1. Первые лежат на
    плоскости s − 1, вторые — на s + 1, а узлы одной плоскости друг с другом
    не соседствуют. Поэтому обновление плоскостей по очереди даёт те же числа,
    что и поточечный обход, но каждая плоскость считается одной операцией numpy.
    """

    def __init__(self, grid):
        nx, ny, nz = grid.shape
        # Сдвиги одномерного индекса к соседям по x, y и z.
        self.strides = (ny * nz, nz, 1)

        # Внутренние узлы: номер плоскости s = i + j + k и одномерный индекс узла.
        i, j, k = np.meshgrid(np.arange(1, nx - 1), np.arange(1, ny - 1),
                              np.arange(1, nz - 1), indexing="ij")
        s = (i + j + k).ravel()
        flat = np.ravel_multi_index((i.ravel(), j.ravel(), k.ravel()), (nx, ny, nz))

        # Сортируем узлы по s и режем список на плоскости.
        order = np.argsort(s, kind="stable")
        s, flat = s[order], flat[order]
        self.planes = np.split(flat, np.flatnonzero(np.diff(s)) + 1)


_WAVEFRONTS = {}


def _wavefront(grid):
    if grid not in _WAVEFRONTS:
        _WAVEFRONTS[grid] = _Wavefront(grid)
    return _WAVEFRONTS[grid]


# --- Итерационные методы: одна итерация --------------------------------------
# Якоби: все шесть соседей берутся с прошлой итерации, весь массив считается
# одной формулой — numpy сначала вычисляет правую часть, потом записывает.
# Зейдель и верхняя релаксация: обход по плоскостям, соседи с меньшими
# индексами уже пересчитаны. omega = 1 — Зейдель, 1 < omega < 2 — SOR.

def jacobi_sweep(T, grid):
    cx, cy, cz = grid.coefficients
    T[1:-1, 1:-1, 1:-1] = (cx * (T[:-2, 1:-1, 1:-1] + T[2:, 1:-1, 1:-1])
                           + cy * (T[1:-1, :-2, 1:-1] + T[1:-1, 2:, 1:-1])
                           + cz * (T[1:-1, 1:-1, :-2] + T[1:-1, 1:-1, 2:])
                           ) / (2 * (cx + cy + cz))


def relaxation_sweep(T, grid, omega):
    """Одна итерация верхней релаксации; при omega = 1 — метод Зейделя."""
    cx, cy, cz = grid.coefficients
    inv_diag = 1 / (2 * (cx + cy + cz))
    front = _wavefront(grid)
    si, sj, sk = front.strides

    # Одномерный вид того же массива: соседи узла — сдвиги индекса на strides.
    flat = T.reshape(-1)
    for idx in front.planes:
        # Значение по Зейделю для всей плоскости: взвешенное среднее шести соседей.
        seidel = (cx * (flat[idx - si] + flat[idx + si])
                  + cy * (flat[idx - sj] + flat[idx + sj])
                  + cz * (flat[idx - sk] + flat[idx + sk])) * inv_diag
        # Зейдель записывает его сразу, верхняя релаксация сдвигает узел к нему в omega раз.
        if omega == 1.0:
            flat[idx] = seidel
        else:
            flat[idx] += omega * (seidel - flat[idx])


# --- Решение задачи ----------------------------------------------------------
# solve собирает всё вместе: граница и начальное поле, выбор метода и параметра,
# итерации до порога невязки. Результат — Solution: поле, число итераций, история
# невязки и время. predicted_iterations — теоретическая оценка ln(1/ε) / ln(1/ρ).

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
          start=None, walls=WALLS, max_iterations=200_000):
    """Итерации до ‖b − Av‖∞ / max(1, ‖b‖∞) ≤ tol.

    method: "jacobi", "seidel" или "sor". Начальное приближение — 20 °C во всех
    внутренних узлах или поле start (например, прошлый расчёт); граничные
    значения всегда берутся новые.
    """
    # 1. Граница по новым данным; внутри — 20 °C или поле прошлого расчёта.
    T = boundary_field(grid, ceiling, walls)
    if start is not None:
        T[1:-1, 1:-1, 1:-1] = start[1:-1, 1:-1, 1:-1]

    # 2. Параметр релаксации: оптимальный (или заданный) для SOR, 1 для Зейделя и Якоби.
    if method == "sor":
        omega = grid.optimal_omega() if omega is None else float(omega)
    elif method == "seidel":
        omega = 1.0
    elif method == "jacobi":
        omega = 1.0
    else:
        raise ValueError(f"неизвестный метод: {method}")

    # 3. Итерации, пока относительная невязка больше tol; время меряется только для них.
    #    Если сходимости нет или невязка стала бесконечной — ошибка.
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
    return Solution(method, grid, T, iterations, residuals, time.perf_counter() - began, omega)


def predicted_iterations(grid, method, tol):
    """Оценка ln(1/tol) / ln(1/ρ) по спектральному радиусу матрицы перехода."""
    rho = grid.jacobi_radius()
    rho = {"jacobi": rho, "seidel": rho**2, "sor": grid.optimal_omega() - 1}[method]
    return np.log(1 / tol) / -np.log(rho)


# --- Точные решения для проверок (разделение переменных) -----------------
# Эталоны, с которыми сравниваются итерации и схема. discrete_exact — точное
# решение сеточной системы без итераций; continuous_increment — ряд Фурье для
# добавки от нагрева в исходной задаче; increment и restrict нужны для проверки
# порядка точности на вложенных сетках.

def _products(a, b, c):
    """a @ b @ c. Accelerate (BLAS numpy на macOS) иногда поднимает ложные
    флаги переполнения в matmul при верном результате; здесь они не нужны."""
    with np.errstate(all="ignore"):
        result = a @ b @ c
    if not np.isfinite(result).all():
        raise ArithmeticError("переполнение при разложении по синусам")
    return result


def _sine_matrix(n, points):
    p = np.arange(1, n)[:, None]
    return np.sin(pi * p * points[None, :])


def _sinh_ratio(mu, steps):
    """sinh(mu·k) / sinh(mu·N) для k = steps (N — последний шаг) без переполнения."""
    mu, steps = np.asarray(mu)[..., None], np.asarray(steps)[None, :]
    total = steps[..., -1:]
    return np.exp(mu * (steps - total)) * (-np.expm1(-2 * mu * steps)) / (-np.expm1(-2 * mu * total))


def _single_face(grid, axis, high, values):
    """Точное решение сеточной задачи, где ненулевые данные только на одной грани.

    values — значения во внутренних узлах грани. По двум касательным осям
    раскладываем по собственным функциям sin(pπi/N); по нормали остаётся
    разностное уравнение с решением sinh(μk)/sinh(μN), cosh μ = 1 + λ/(2c).
    """
    n = (grid.nx, grid.ny, grid.nz)
    c = grid.coefficients
    a, b = [ax for ax in range(3) if ax != axis]

    # Раскладываем данные грани по синусам вдоль двух касательных осей.
    sa = _sine_matrix(n[a], np.arange(1, n[a]) / n[a])
    sb = _sine_matrix(n[b], np.arange(1, n[b]) / n[b])
    coef = (2 / n[a]) * (2 / n[b]) * _products(sa, values, sb.T)

    # Для каждой гармоники — множитель по нормали к грани: sinh(μk) / sinh(μN).
    p = np.arange(1, n[a])[:, None]
    q = np.arange(1, n[b])[None, :]
    lam = (4 * c[a] * np.sin(pi * p / (2 * n[a])) ** 2
           + 4 * c[b] * np.sin(pi * q / (2 * n[b])) ** 2)
    mu = np.arccosh(1 + lam / (2 * c[axis]))
    ratio = _sinh_ratio(mu.ravel(), np.arange(n[axis] + 1)).reshape(*mu.shape, n[axis] + 1)
    if not high:
        ratio = ratio[..., ::-1]

    # Собираем решение во внутренних узлах обратно из гармоник.
    inner = np.einsum("pi,pqk,qj->ijk", sa, coef[..., None] * ratio, sb)[..., 1:-1]
    return np.moveaxis(inner, [0, 1, 2], [a, b, axis])


def discrete_exact(grid, ceiling=DEFAULT_CEILING, walls=WALLS):
    """Точное решение сеточной системы: сумма шести задач с одной ненулевой гранью."""
    T = boundary_field(grid, ceiling, walls)
    interior = np.zeros((grid.nx - 1, grid.ny - 1, grid.nz - 1))
    faces = [(0, False, T[0, 1:-1, 1:-1]), (0, True, T[-1, 1:-1, 1:-1]),
             (1, False, T[1:-1, 0, 1:-1]), (1, True, T[1:-1, -1, 1:-1]),
             (2, False, T[1:-1, 1:-1, 0]), (2, True, T[1:-1, 1:-1, -1])]
    for axis, high, values in faces:
        interior += _single_face(grid, axis, high, values)
    T[1:-1, 1:-1, 1:-1] = interior
    return T


def continuous_increment(grid, ceiling=DEFAULT_CEILING, modes=96, quadrature=1536):
    """Добавка от нагрева потолка для дифференциальной задачи, в узлах сетки.

    Это решение с данными θ = T_пот − 20 на потолке и нулём на остальных гранях:
    θ = Σ a_pq sin(pπx/Lx) sin(qπy/Ly) sinh(k_pq z) / sinh(k_pq Lz).
    Данные гладкие и на краю потолка обращаются в нуль, поэтому ряд сходится
    быстро и годится эталоном для проверки второго порядка.
    """
    # Коэффициенты Фурье данных потолка θ = φ₆ − 20 (квадратура на мелкой сетке).
    n = quadrature
    u = np.arange(1, n) / n
    theta = ceiling_temperature(u[:, None] * LX, u[None, :] * LY, ceiling) - T_BACKGROUND
    s = _sine_matrix(n, u)[:modes]
    coef = (2 / n) ** 2 * _products(s, theta, s.T)

    # Волновые числа гармоник и их затухание по высоте: sinh(kz) / sinh(kLz).
    p = np.arange(1, modes + 1)[:, None]
    q = np.arange(1, modes + 1)[None, :]
    k = pi * np.sqrt((p / LX) ** 2 + (q / LY) ** 2)
    x, y, _ = grid.axes
    ratio = _sinh_ratio(k.ravel() * LZ / grid.nz, np.arange(grid.nz + 1)).reshape(*k.shape, grid.nz + 1)

    # Сумма ряда в узлах сетки.
    bx = np.sin(pi * np.arange(1, modes + 1)[:, None] * x[None, :] / LX)
    by = np.sin(pi * np.arange(1, modes + 1)[:, None] * y[None, :] / LY)
    return np.einsum("pi,pqk,qj->ijk", bx, coef[..., None] * ratio, by)


def increment(grid, ceiling=DEFAULT_CEILING, walls=WALLS, tol=1e-10):
    """Добавка к фону: T при заданном нагреве минус T при A = 0 с теми же стенами.

    Задача линейна, поэтому добавка не зависит от температур стен: это решение
    с нулём на стенах и полу и данными T_пот − 20 на потолке.
    """
    heated = solve(grid, ceiling, tol=tol, walls=walls)
    background = solve(grid, replace(ceiling, amplitude=0.0), tol=tol, walls=walls)
    return heated.T - background.T


def restrict(fine, coarse_grid):
    """Значения мелкой сетки в узлах вложенной вдвое более грубой."""
    return fine[::2, ::2, ::2][: coarse_grid.nx + 1, : coarse_grid.ny + 1, : coarse_grid.nz + 1]
