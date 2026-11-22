"""Проверки решателя: python -m unittest test_heat_room"""

import unittest

import numpy as np

from heat_room import (DEFAULT_CEILING, LX, LY, T_WALL, Grid, boundary_field, ceiling_temperature,
                       continuous_exact, discrete_exact, relaxation_sweep, restrict, solve)


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


class HeatRoomTests(unittest.TestCase):
    def test_ceiling_meets_walls_at_20_degrees(self):
        x = np.linspace(0, LX, 81)
        y = np.linspace(0, LY, 61)
        c = ceiling_temperature(x[:, None], y[None, :])
        for edge in (c[0], c[-1], c[:, 0], c[:, -1]):
            np.testing.assert_allclose(edge, T_WALL, atol=1e-12)
        self.assertGreater(c.max(), 55.0)

    def test_wavefront_sweep_equals_pointwise_lexicographic_sweep(self):
        grid = Grid(6, 5, 4)
        rng = np.random.default_rng(1)
        start = boundary_field(grid) + rng.normal(size=grid.shape) * np.pad(
            np.ones((grid.nx - 1, grid.ny - 1, grid.nz - 1)), 1)
        for omega in (1.0, 1.6):
            a, b = start.copy(), start.copy()
            relaxation_sweep(a, grid, omega)
            pointwise_sweep(b, grid, omega)
            np.testing.assert_allclose(a, b, rtol=0, atol=1e-12)

    def test_all_methods_reach_the_direct_solution(self):
        grid = Grid.with_step(0.2)
        exact = discrete_exact(grid)
        iterations = {}
        for method in ("jacobi", "seidel", "sor"):
            sol = solve(grid, method=method, tol=1e-10)
            iterations[method] = sol.iterations
            np.testing.assert_allclose(sol.T, exact, rtol=0, atol=1e-6)
        self.assertLess(iterations["sor"] * 5, iterations["seidel"])
        self.assertAlmostEqual(iterations["jacobi"] / iterations["seidel"], 2.0, delta=0.25)

    def test_maximum_principle(self):
        sol = solve(Grid.with_step(0.2), tol=1e-10)
        inner = sol.T[1:-1, 1:-1, 1:-1]
        self.assertGreaterEqual(inner.min(), T_WALL)
        self.assertLessEqual(inner.max(), sol.T[:, :, -1].max())

    def test_second_order_on_nested_grids(self):
        errors, fields = [], []
        for h in (0.2, 0.1):
            grid = Grid.with_step(h)
            T = discrete_exact(grid)
            fields.append((grid, T))
            errors.append(np.abs(T - continuous_exact(grid)).max())
        order = np.log2(errors[0] / errors[1])
        self.assertGreater(order, 1.7)
        diff = np.abs(restrict(fields[1][1], fields[0][0]) - fields[0][1]).max()
        self.assertLess(diff, errors[0] * 1.5)

    def test_warm_start_keeps_new_boundary(self):
        grid = Grid.with_step(0.2)
        first = solve(grid, tol=1e-8)
        hotter = DEFAULT_CEILING.__class__(amplitude=80.0)
        second = solve(grid, hotter, tol=1e-8, start=first.T)
        np.testing.assert_allclose(second.T, discrete_exact(grid, hotter), atol=1e-4)


if __name__ == "__main__":
    unittest.main()
