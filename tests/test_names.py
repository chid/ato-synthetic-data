import random
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_names as names


class NameTests(unittest.TestCase):
    def test_cli_generates_reproducible_names(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/generate_names.py"), "--n", "5", "--seed", "42"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout, (
            "first_name,last_name,full_name\n"
            "Danielle,Johnson,Danielle Johnson\n"
            "Joshua,Walker,Joshua Walker\n"
            "Jill,Rhodes,Jill Rhodes\n"
            "Patricia,Miller,Patricia Miller\n"
            "Robert,Johnson,Robert Johnson\n"
        ))

    def test_seed_controls_names_without_changing_global_random_state(self):
        random.seed(123)
        state = random.getstate()
        first = names.generate_names(20, seed=42, sexes=["Male", "Female"] * 10)
        pd.testing.assert_frame_equal(first, names.generate_names(20, seed=42, sexes=["Male", "Female"] * 10))
        self.assertFalse(first.equals(names.generate_names(20, seed=43, sexes=["Male", "Female"] * 10)))
        self.assertEqual(random.getstate(), state)
        self.assertTrue((first["full_name"] == first["first_name"] + " " + first["last_name"]).all())

    def test_seed_sequence_support_does_not_spawn_new_children(self):
        seed = np.random.SeedSequence(42).spawn(1)[0]
        first = names.generate_names(10, seed=seed)
        pd.testing.assert_frame_equal(first, names.generate_names(10, seed=seed))
        self.assertEqual(seed.n_children_spawned, 0)

    def test_adding_names_preserves_record_values_and_index(self):
        population = pd.DataFrame({
            "sex": ["Female", "Male", "Unknown"],
            "taxable_income": [100.0, 200.0, 300.0],
        }, index=[7, 2, 99])
        result = names.add_names(population, seed=42)
        pd.testing.assert_frame_equal(result.drop(columns=names.NAME_COLUMNS), population)
        self.assertFalse(result[names.NAME_COLUMNS].isna().any().any())
        self.assertTrue((result[names.NAME_COLUMNS].map(len) > 0).all().all())
        self.assertEqual(list(population.columns), ["sex", "taxable_income"])

    def test_names_remain_stable_for_each_longitudinal_agent(self):
        population = pd.DataFrame({
            "agent_id": ["t0-0", "t0-1", "t0-1", "2024-new-0", "t0-0"],
            "sex": ["Female", "Male", "Male", "Female", "Female"],
            "year": [2023, 2023, 2024, 2024, 2024],
            "taxable_income": [100.0, 200.0, 220.0, 50.0, 110.0],
        })
        result = names.add_names(population, seed=42)
        pd.testing.assert_frame_equal(result.drop(columns=names.NAME_COLUMNS), population)
        self.assertTrue((result.groupby("agent_id")[names.NAME_COLUMNS].nunique() == 1).all().all())
        self.assertFalse(result[names.NAME_COLUMNS].isna().any().any())

    def test_empty_and_invalid_counts(self):
        empty = names.generate_names(0)
        self.assertTrue(empty.empty)
        self.assertEqual(list(empty.columns), ["first_name", "last_name", "full_name"])
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            names.generate_names(-1)
        with self.assertRaisesRegex(ValueError, "one value per name"):
            names.generate_names(2, sexes=["Female"])

    def test_cli_rejects_negative_count(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/generate_names.py"), "--n", "-1"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--n must be nonnegative", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
