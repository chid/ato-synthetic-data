import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backtest_2012_13 as backtest
import generate_synthetic as gen


class SignedItemTests(unittest.TestCase):
    def test_rental_losses_keep_the_source_sign_and_mean(self):
        cells = pd.DataFrame({
            "Individuals | count": np.full(20000, 1000),
            "Net rent - loss | count": np.full(20000, 250),
            "Net rent - loss | dollars": np.full(20000, -250000),
        })

        losses = gen.draw_items(np.random.default_rng(42), cells)["net_rent_loss"]

        self.assertTrue(np.any(losses < 0), "Rental losses were all zero")
        self.assertTrue(np.all(losses <= 0), "Rental losses must not become profits")
        self.assertAlmostEqual(np.mean(losses != 0), 0.25, delta=0.01)
        self.assertAlmostEqual(losses.mean(), -250, delta=15)

    def test_positive_and_zero_items_keep_their_mean_and_presence(self):
        cells = pd.DataFrame({
            "Individuals | count": np.full(20000, 1000),
            "Net rent - profit | count": np.full(20000, 1000),
            "Net rent - profit | dollars": np.full(20000, 1000000),
            "Net rent - loss | count": np.zeros(20000),
            "Net rent - loss | dollars": np.zeros(20000),
        })

        items = gen.draw_items(np.random.default_rng(42), cells)

        self.assertTrue(np.all(items["net_rent_profit"] > 0))
        self.assertAlmostEqual(items["net_rent_profit"].mean(), 1000, delta=25)
        np.testing.assert_array_equal(items["net_rent_loss"], np.zeros(20000))

    def test_2013_population_preserves_rental_losses(self):
        source = pd.DataFrame({
            "Individuals | count": [1000],
            "Gender": ["Male"],
            "Taxable status": ["Non Taxable"],
            "Age": ["c. 25 - 29"],
            "income_lo": [0],
            "income_hi": [6000],
            "taxable_income_mean": [3000],
            "Net rent – loss | count": [1000],
            "Net rent – loss | dollars": [-1000000],
        })

        with patch.object(backtest, "load_table3_2013", return_value=source):
            population = backtest.generate_2013_population(1000, seed=42)

        self.assertTrue(
            (population["net_rent_loss"] < 0).all(),
            "The 2013 backtest discarded signed rental losses",
        )
        self.assertAlmostEqual(population["net_rent_loss"].mean(), -1000, delta=100)


if __name__ == "__main__":
    unittest.main()
