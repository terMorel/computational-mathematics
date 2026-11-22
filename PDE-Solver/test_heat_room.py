"""Проверки решателя: python -m unittest test_heat_room"""

from dataclasses import replace
import itertools
import unittest

import numpy as np

from heat_room import (DEFAULT_CEILING, LX, LY, T_BACKGROUND, WALLS, Grid, boundary_field,
                       ceiling_temperature, continuous_increment, discrete_exact, increment,
                       relaxation_sweep, restrict, solve)

GRID = Grid.with_step(0.2)   # 20 × 15 × 13 шагов


def pointwise_sweep(T, grid, omega):
    """Обход узлов по учебнику: (1,1,1), (1,1,2), …, по одному узлу за шаг."""
    cx, cy, cz = grid.coefficients
    d = 2 * (cx + cy + cz)
    for i in range(1, grid.nx):
        for j in range(1, grid.ny):
            for k in range(1, grid.nz):
                seidel = (cx * (T[i - 1, j, k] + T[i + 1, j, k]) + cy * (T[i, j - 1, k] + T[i, j + 1, k])
                          + cz * (T[i, j, k - 1] + T[i, j, k + 1])) / d
                T[i, j, k] += omega * (seidel - T[i, j, k])


def assembled_solution(grid, T):
    """Независимая сборка сеточной системы по узлам и прямое решение."""
    nx, ny, nz = grid.shape
    cx, cy, cz = grid.coefficients
    number = -np.ones(grid.shape, dtype=int)
    inner = list(itertools.product(range(1, nx - 1), range(1, ny - 1), range(1, nz - 1)))
    for row, node in enumerate(inner):
        number[node] = row
    A = np.zeros((len(inner), len(inner)))
    b = np.zeros(len(inner))
    for row, (i, j, k) in enumerate(inner):
        A[row, row] = 2 * (cx + cy + cz)
        for di, dj, dk, c in [(-1, 0, 0, cx), (1, 0, 0, cx), (0, -1, 0, cy),
                              (0, 1, 0, cy), (0, 0, -1, cz), (0, 0, 1, cz)]:
            neighbour = (i + di, j + dj, k + dk)
            if number[neighbour] >= 0:
                A[row, number[neighbour]] -= c
            else:
                b[row] += c * T[neighbour]
    return np.linalg.solve(A, b).reshape(nx - 2, ny - 2, nz - 2)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.T = boundary_field(GRID)

    def test_open_faces(self):
        T, w = self.T, WALLS
        for face, value in [(T[0, 1:-1, 1:-1], w.x0), (T[-1, 1:-1, 1:-1], w.x1),
                            (T[1:-1, 0, 1:-1], w.y0), (T[1:-1, -1, 1:-1], w.y1),
                            (T[1:-1, 1:-1, 0], w.floor)]:
            np.testing.assert_array_equal(face, value)
        x, y, _ = GRID.axes
        np.testing.assert_allclose(T[1:-1, 1:-1, -1],
                                   ceiling_temperature(x[1:-1, None], y[None, 1:-1]), rtol=0, atol=0)

    def test_ceiling_formula_tends_to_20_at_its_edge(self):
        x = np.linspace(0, LX, 81)
        y = np.linspace(0, LY, 61)
        c = ceiling_temperature(x[:, None], y[None, :])
        for edge in (c[0], c[-1], c[:, 0], c[:, -1]):
            np.testing.assert_allclose(edge, T_BACKGROUND, atol=1e-12)

    def test_all_edges_and_vertices_follow_the_averaging_rule(self):
        T, w = self.T, WALLS
        limits = {("x", 0): w.x0, ("x", 1): w.x1, ("y", 0): w.y0, ("y", 1): w.y1,
                  ("z", 0): w.floor, ("z", 1): T_BACKGROUND}
        last = {"x": -1, "y": -1, "z": -1}
        edges = 0
        for (a, b) in [("x", "y"), ("x", "z"), ("y", "z")]:
            for sa, sb in itertools.product((0, 1), repeat=2):
                index = [slice(1, -1)] * 3
                index["xyz".index(a)] = -1 if sa else 0
                index["xyz".index(b)] = -1 if sb else 0
                expected = (limits[(a, sa)] + limits[(b, sb)]) / 2
                np.testing.assert_array_equal(T[tuple(index)], expected)
                edges += 1
        self.assertEqual(edges, 12)
        for sx, sy, sz in itertools.product((0, 1), repeat=3):
            expected = (limits[("x", sx)] + limits[("y", sy)] + limits[("z", sz)]) / 3
            vertex = (-1 if sx else 0, -1 if sy else 0, -1 if sz else 0)
            self.assertAlmostEqual(T[vertex], expected, places=12)
        self.assertEqual(T[0, 0, 5], 17.0)   # ребро x = y = 0
        self.assertEqual(T[0, 0, 0], 18.0)   # вершина (0, 0, 0)

    def test_edges_and_vertices_do_not_enter_interior_equations(self):
        """Подставляем на все рёбра и вершины 1000 °C: итерация не меняет решение."""
        start = solve(GRID, tol=1e-12).T
        changed = boundary_field(GRID)
        i, j, k = np.indices(GRID.shape)
        extreme = (((i == 0) | (i == GRID.nx)).astype(int) + ((j == 0) | (j == GRID.ny))
                   + ((k == 0) | (k == GRID.nz)))
        changed[extreme >= 2] = 1000.0
        T = changed.copy()
        T[1:-1, 1:-1, 1:-1] = start[1:-1, 1:-1, 1:-1]
        relaxation_sweep(T, GRID, 1.0)
        np.testing.assert_allclose(T[1:-1, 1:-1, 1:-1], start[1:-1, 1:-1, 1:-1], rtol=0, atol=1e-9)


class SolverTests(unittest.TestCase):
    def test_wavefront_sweep_equals_pointwise_lexicographic_sweep(self):
        grid = Grid(6, 5, 4)
        rng = np.random.default_rng(1)
        start = boundary_field(grid)
        start[1:-1, 1:-1, 1:-1] += rng.normal(size=(5, 4, 3))
        for omega in (1.0, 1.6):
            a, b = start.copy(), start.copy()
            relaxation_sweep(a, grid, omega)
            pointwise_sweep(b, grid, omega)
            np.testing.assert_allclose(a, b, rtol=0, atol=1e-12)

    def test_separation_of_variables_matches_assembled_system(self):
        grid = Grid(10, 8, 7)
        T = boundary_field(grid)
        np.testing.assert_allclose(discrete_exact(grid)[1:-1, 1:-1, 1:-1], assembled_solution(grid, T),
                                   rtol=0, atol=1e-10)

    def test_all_methods_reach_the_exact_grid_solution(self):
        exact = discrete_exact(GRID)
        iterations = {}
        for method in ("jacobi", "seidel", "sor"):
            sol = solve(GRID, method=method, tol=1e-10)
            iterations[method] = sol.iterations
            np.testing.assert_allclose(sol.T, exact, rtol=0, atol=1e-6)
        self.assertLess(iterations["sor"] * 5, iterations["seidel"])
        self.assertAlmostEqual(iterations["jacobi"] / iterations["seidel"], 2.0, delta=0.25)

    def test_maximum_principle(self):
        T = solve(GRID, tol=1e-10).T
        inner = T[1:-1, 1:-1, 1:-1]
        self.assertGreaterEqual(inner.min(), WALLS.coldest)
        self.assertLessEqual(inner.max(), T[:, :, -1].max())

    def test_zero_amplitude_keeps_walls_and_gives_nonuniform_field(self):
        T = solve(GRID, replace(DEFAULT_CEILING, amplitude=0.0), tol=1e-10).T
        np.testing.assert_array_equal(T[1:-1, 1:-1, -1], T_BACKGROUND)
        np.testing.assert_array_equal(T[0, 1:-1, 1:-1], WALLS.x0)
        np.testing.assert_array_equal(T[-1, 1:-1, 1:-1], WALLS.x1)
        inner = T[1:-1, 1:-1, 1:-1]
        self.assertLess(inner.min(), 17.0)
        self.assertGreater(inner.max(), 23.0)

    def test_increment_is_second_order(self):
        errors, fields = [], []
        for h in (0.2, 0.1):
            grid = Grid.with_step(h)
            theta = increment(grid, tol=1e-11)
            fields.append((grid, theta))
            errors.append(np.abs(theta - continuous_increment(grid)).max())
        self.assertGreater(np.log2(errors[0] / errors[1]), 1.7)
        diff = np.abs(restrict(fields[1][1], fields[0][0]) - fields[0][1]).max()
        self.assertLess(diff, errors[0] * 1.5)

    def test_warm_start_keeps_new_boundary(self):
        first = solve(GRID, tol=1e-8)
        hotter = replace(DEFAULT_CEILING, amplitude=80.0)
        second = solve(GRID, hotter, tol=1e-8, start=first.T)
        np.testing.assert_allclose(second.T, discrete_exact(GRID, hotter), atol=1e-4)


if __name__ == "__main__":
    unittest.main()
