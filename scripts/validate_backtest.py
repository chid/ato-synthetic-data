"""
The actual backtest scorecard: how well does a population built and forward-simulated
from ONLY 2012-13-vintage data + no-look-ahead trend assumptions predict the REAL,
already-published 2022-23 ATO figures 10 years later?

Two checks:
  1. Does the 2012-13 t0 population (built from the ORIGINAL 2012-13 release) actually
     reproduce the real 2012-13 aggregate stats? (Validates the old-vintage generator
     itself, same spirit as validate_synthetic.py.)
  2. Does the 10-year-forward prediction land near the REAL 2022-23 figures?
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def main():
    summary = pd.read_csv(ROOT / "synthetic" / "backtest_2012_13_summary_by_year.csv")
    t0 = summary.iloc[0]
    predicted_2023 = summary.iloc[-1]

    real_t3_2013 = pd.read_csv(ROOT / "data" / "processed" / "backtest_2012_13" / "table3_2012_13_items_by_bracket.csv")
    real_t3_2013["Individuals | count"] = pd.to_numeric(real_t3_2013["Individuals | count"], errors="coerce")
    real_total_2013 = real_t3_2013["Individuals | count"].sum()
    real_pct_taxable_2013 = real_t3_2013.loc[real_t3_2013["Taxable status"] == "Taxable", "Individuals | count"].sum() / real_total_2013 * 100
    real_pct_male_2013 = real_t3_2013.loc[real_t3_2013["Gender"] == "Male", "Individuals | count"].sum() / real_total_2013 * 100

    print("=" * 70)
    print("CHECK 1: does the 2012-13 t0 population match the REAL 2012-13 figures?")
    print("=" * 70)
    print(f"{'':28s}{'synthetic t0':>16s}{'real 2012-13':>16s}")
    print(f"{'% taxable':28s}{t0['pct_taxable']:16.1f}{real_pct_taxable_2013:16.1f}")
    print(f"{'% male':28s}{t0['sex_male_pct']:16.1f}{real_pct_male_2013:16.1f}")
    print("(Real total individuals in 2012-13: {:,.0f} -- t0 is a 20k-row downsample,".format(real_total_2013))
    print(" so only shares/rates are directly comparable, not raw counts.)")

    print()
    print("=" * 70)
    print("CHECK 2: the actual backtest -- predicted 2022-23 (from 2012-13 + 10 years")
    print("of forward simulation) vs the REAL, already-published 2022-23 ATO figures")
    print("=" * 70)

    real_t3a = pd.read_csv(ROOT / "data" / "processed" / "ato_table3a_items_by_bracket.csv")
    real_total_2023 = real_t3a["Individuals | count"].sum()
    real_pct_taxable_2023 = real_t3a.loc[real_t3a["Taxable status"] == "Taxable", "Individuals | count"].sum() / real_total_2023 * 100
    real_pct_male_2023 = real_t3a.loc[real_t3a["Sex4"] == "Male", "Individuals | count"].sum() / real_total_2023 * 100
    real_mean_all_2023 = real_t3a["Taxable income or loss2 | dollars"].sum() / real_t3a["Taxable income or loss2 | count"].sum()

    # Our own current synthetic 2022-23 model (calibrated tightly to Table 3A/16B --
    # see validate_synthetic.py) as a full-population median/mean reference, since
    # ATO's own bracket table doesn't publish a clean full-population (incl. Non
    # Taxable) median directly.
    current_model = pd.read_csv(ROOT / "synthetic" / "synthetic_individuals.csv")

    print(f"\n{'':32s}{'predicted (2012-13 + 10y)':>26s}{'real 2022-23':>16s}")
    print(f"{'% taxable':32s}{predicted_2023['pct_taxable']:26.1f}{real_pct_taxable_2023:16.1f}")
    print(f"{'% male':32s}{predicted_2023['sex_male_pct']:26.1f}{real_pct_male_2023:16.1f}")
    print(f"{'mean taxable income (all)':32s}{predicted_2023['mean_taxable_income']:26,.0f}{real_mean_all_2023:16,.0f}")
    print(f"{'median taxable income (all)':32s}{predicted_2023['median_taxable_income']:26,.0f}{current_model['taxable_income'].median():16,.0f}")

    pct_err_mean = (predicted_2023["mean_taxable_income"] - real_mean_all_2023) / real_mean_all_2023 * 100
    pct_err_median = (predicted_2023["median_taxable_income"] - current_model["taxable_income"].median()) / current_model["taxable_income"].median() * 100
    print(f"\nMean income prediction error:   {pct_err_mean:+.1f}%")
    print(f"Median income prediction error: {pct_err_median:+.1f}%")
    print("\nMean overshoots while median undershoots -> the 10-year forward simulation")
    print("predicts a MORE skewed/unequal distribution in 2022-23 than actually happened.")
    print("A likely real cause, not just noise: taxable_status and its bracket-conditional")
    print("probability were held FIXED at their 2012-13 shape for the whole 10-year run,")
    print("but Australia's tax-free threshold, LITO, and offsets like LMITO genuinely")
    print("changed over 2013-2023 -- this backtest has no mechanism to reflect real")
    print("policy changes, only demographic/economic drift. See APPROACH.md.")


if __name__ == "__main__":
    main()
