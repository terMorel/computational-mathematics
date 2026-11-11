from dataclasses import replace
import unittest

import numpy as np

from solve import bisection, calculate, norm, problems


class NonlinearEquationsTests(unittest.TestCase):
    def test_midpoint_zero_still_requires_a_narrow_interval(self):
        problem = replace(
            problems()[0],
            function=lambda z: np.array([z[0] - 0.3]),
            reduced=lambda x: x - 0.3,
        )
        result = bisection(problem, 1e-10, 200)
        self.assertGreater(result.iterations, 1)
        self.assertLessEqual((result.interval[1] - result.interval[0])/2, 1e-10)
        self.assertLessEqual(norm(problem.function(result.solution)), 1e-10)

    def test_reduced_zero_does_not_bypass_original_residual(self):
        # Несогласованная формула после исключения переменной должна
        # приводить к сбою проверки, а не к ложному успешному результату.
        problem = replace(problems()[0], reduced=lambda x: x - 0.3)
        with self.assertRaises((ArithmeticError, RuntimeError)):
            bisection(problem, 1e-10, 200)

    def test_all_solutions_meet_the_accuracy_requirement(self):
        reference = (
            (0.3040135965927,),
            (0.7548776662467,),
            (3.355911738828, 1.206906817516),
            (1.791338609964, -0.344221036407),
        )
        for (problem, results), expected in zip(calculate(), reference):
            self.assertEqual(len(results), 4)
            for result in results:
                with self.subTest(problem=problem.name, method=result.method):
                    self.assertLessEqual(norm(problem.function(result.solution)), 1e-10)
                    np.testing.assert_allclose(result.solution, expected, rtol=0, atol=1e-10)

    def test_iteration_stops_after_both_criteria_are_satisfied(self):
        problem, results = calculate()[2]
        result = results[1]
        first_small_residual = next(k for k, value in enumerate(result.residuals)
                                    if value <= 1e-10)
        self.assertLess(first_small_residual, result.iterations)
        previous = np.array(problem.start)
        for _ in range(result.iterations):
            current = problem.iteration(previous)
            error_bound = problem.contraction/(1-problem.contraction) * norm(current-previous)
            previous = current
        self.assertLessEqual(error_bound, 1e-10)
        self.assertLessEqual(norm(problem.function(current)), 1e-10)


if __name__ == "__main__":
    unittest.main()
