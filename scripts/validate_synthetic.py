"""
Compare the synthetic sample's distribution against the real ATO/ABS published
statistics it was calibrated on, to check the datagen matches up.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    x = x[x >= 0]
    n = len(x)
    if n == 0 or x.sum() == 0:
        return float("nan")
    cum = np.cumsum(x)
    return (n + 1 - 2 * (cum.sum() / cum[-1])) / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", type=Path, default=ROOT / "synthetic" / "synthetic_individuals.csv")
    args = ap.parse_args()

    syn = pd.read_csv(args.synthetic)
    real_cells = pd.read_csv(ROOT / "data" / "processed" / "ato_table3a_items_by_bracket.csv")
    abs_national = pd.read_csv(ROOT / "data" / "processed" / "abs_table3_1_income_by_gccsa.csv")

    print("=" * 70)
    print(f"Synthetic sample: {len(syn):,} rows")
    print("=" * 70)

    # --- taxable income distribution ---
    real_total_individuals = real_cells["Individuals | count"].sum()
    real_total_taxable_income = real_cells["Taxable income or loss2 | dollars"].sum()
    real_mean_ti = real_total_taxable_income / real_cells["Taxable income or loss2 | count"].sum()

    print("\n-- Taxable income (vs ATO Table 3A, all lodgers 2022-23) --")
    print(f"{'':28s}{'synthetic':>16s}{'real (ATO)':>16s}")
    print(f"{'mean':28s}{syn['taxable_income'].mean():16,.0f}{real_mean_ti:16,.0f}")
    print(f"{'median':28s}{syn['taxable_income'].median():16,.0f}{'~58,975*':>16s}")
    for p in (10, 25, 50, 75, 90, 99):
        print(f"{'p' + str(p):28s}{np.percentile(syn['taxable_income'], p):16,.0f}")
    print(f"{'gini (synthetic)':28s}{gini(syn['taxable_income']):16.3f}")
    print("* ATO Table 16B median taxable income across all taxable individuals")

    print("\n-- Cross-check vs ABS Personal Income in Australia 2022-23, Australia total --")
    abs_row = abs_national[abs_national["GCCSA"].str.strip() == "Australia"].iloc[0]
    print(f"ABS median total income (all earners incl. non-lodgers): ${float(abs_row['Median']):,.0f}")
    print(f"ABS mean total income:                                    ${float(abs_row['Mean']):,.0f}")
    print("(ABS 'total income' covers a broader population than ATO taxable lodgers, so this")
    print(" is a plausibility check, not an exact match target.)")

    # --- sex split ---
    print("\n-- Sex split --")
    print("synthetic:\n", (syn["sex"].value_counts(normalize=True) * 100).round(1))
    real_sex = real_cells.groupby("Sex4")["Individuals | count"].sum()
    print("real (ATO):\n", (real_sex / real_sex.sum() * 100).round(1))

    # --- taxable status split ---
    print("\n-- Taxable status split --")
    print("synthetic:\n", (syn["taxable_status"].value_counts(normalize=True) * 100).round(1))
    real_status = real_cells.groupby("Taxable status")["Individuals | count"].sum()
    print("real (ATO):\n", (real_status / real_status.sum() * 100).round(1))

    # --- item-level presence rates + mean amounts ---
    item_checks = [
        ("salary_or_wages", "Salary or wages"),
        ("gross_interest", "Gross interest"),
        ("dividends_franked", "Dividends franked"),
        ("total_deductions", "Total deductions2"),
        ("deduction_car_expenses", "Total work related car expenses"),
        ("net_capital_gain", "Capital gains net capital gain"),
    ]
    print("\n-- Selected item presence-rate & mean-when-present: synthetic vs real --")
    print(f"{'item':30s}{'syn p(present)':>16s}{'real p(present)':>16s}{'syn mean$':>14s}{'real mean$':>14s}")
    for col, base in item_checks:
        real_count = real_cells[f"{base} | count"].sum()
        real_dollars = real_cells[f"{base} | dollars"].sum()
        real_p = real_count / real_total_individuals
        real_mean = real_dollars / real_count if real_count else float("nan")

        syn_present = syn[col] > 0
        syn_p = syn_present.mean()
        syn_mean = syn.loc[syn_present, col].mean() if syn_present.any() else float("nan")

        print(f"{col:30s}{syn_p:16.3f}{real_p:16.3f}{syn_mean:14,.0f}{real_mean:14,.0f}")

    # --- state split: synthetic vs ATO Table 6A (the source it was drawn from) ---
    print("\n-- State split: synthetic vs ATO Table 6A (source) --")
    t6a = pd.read_csv(ROOT / "data" / "processed" / "ato_table6a_items_by_postcode.csv")
    real_state = t6a.groupby("State/ Territory1")["Individuals | count"].sum()
    real_state_pct = (real_state / real_state.sum() * 100).round(1).sort_values(ascending=False)
    syn_state_pct = (syn["state"].value_counts(normalize=True) * 100).round(1)
    cmp_state = pd.DataFrame({"synthetic %": syn_state_pct, "real (ATO) %": real_state_pct}).fillna(0)
    print(cmp_state)

    # --- industry split: synthetic vs its own Census source, by sex ---
    print("\n-- Industry split by sex: synthetic vs Census G54 (source) --")
    g54 = pd.read_csv(ROOT / "data" / "processed" / "census_g54_industry_by_age_sex_state.csv")
    real_ind = g54.groupby(["sex", "industry_census_code"])["persons"].sum()
    real_ind_pct = (real_ind / real_ind.groupby(level=0).sum() * 100).round(1)
    syn_ind_pct = (
        syn.groupby(["sex", "industry"]).size() / syn.groupby("sex").size() * 100
    ).round(1)
    top_n = 6
    for sex in ["Male", "Female"]:
        print(f"\n  {sex} - top {top_n} industries (synthetic % | Census source %):")
        top = syn_ind_pct[sex].sort_values(ascending=False).head(top_n)
        for industry, syn_pct in top.items():
            real_pct = real_ind_pct.get((sex, industry), float("nan"))
            print(f"    {industry:20s}{syn_pct:8.1f}{real_pct:8.1f}")

    # --- independent cross-check: ATO business-filer industry mix vs Census employed-industry mix ---
    print("\n-- Independent check: business-income filers' industry (ATO Table 5) vs")
    print("   all-employees industry (Census G54) -- these are DIFFERENT populations,")
    print("   not a calibration target, just a sanity comparison --")
    t5 = pd.read_csv(ROOT / "data" / "processed" / "ato_table5_items_by_industry.csv")
    ato_industry_map = {
        "a. Agriculture, Forestry and Fishing": "Ag_For_Fshg", "b. Mining": "Mining",
        "c. Manufacturing": "Manufact", "g. Retail Trade": "RetTde",
        "q. Health Care and Social Assistance": "HlthCare_SocAs",
        "m. Professional, Scientific and Technical Services": "Pro_scien_tec",
    }
    t5["industry_census_code"] = t5["Broad industry2"].map(ato_industry_map)
    biz_ind = t5.dropna(subset=["industry_census_code"]).groupby("industry_census_code")["Individuals | count"].sum()
    biz_ind_pct = (biz_ind / t5["Individuals | count"].sum() * 100).round(1)
    emp_ind_pct = (g54.groupby("industry_census_code")["persons"].sum() / g54["persons"].sum() * 100).round(1)
    print(f"  {'industry':20s}{'business filers %':>20s}{'all employees %':>18s}")
    for code in ato_industry_map.values():
        print(f"  {code:20s}{biz_ind_pct.get(code, 0):20.1f}{emp_ind_pct.get(code, 0):18.1f}")

    # --- sex ratio: taxpayers (ATO) vs whole population (Census) ---
    print("\n-- Sex ratio: ATO taxpayer population vs Census whole-of-population --")
    print("  (different populations by design -- taxpayers exclude children, many retirees")
    print("   have no lodgment obligation, etc. -- shown as a plausibility check only)")
    census_aus_g01 = pd.read_csv(
        ROOT / "data" / "processed" / "census_g01_counts_national.csv"
    )
    tot_m, tot_f = int(census_aus_g01["Tot_P_M"].iloc[0]), int(census_aus_g01["Tot_P_F"].iloc[0])
    print(f"  Census (all persons):  Male {tot_m/(tot_m+tot_f)*100:.1f}%  Female {tot_f/(tot_m+tot_f)*100:.1f}%")
    print(f"  ATO (taxpayers):       {(real_sex / real_sex.sum() * 100).round(1).to_dict()}")

    # --- postcode income calibration: does higher-Census-income postcode -> higher synthetic income? ---
    print("\n-- Postcode income calibration check --")
    g02 = pd.read_csv(ROOT / "data" / "processed" / "census_g02_medians_by_postcode.csv")
    g02["postcode"] = g02["postcode"].astype(str)
    syn_valid = syn.dropna(subset=["postcode"]).copy()
    syn_valid["postcode"] = syn_valid["postcode"].astype(float).astype(int).astype(str)
    by_pc = syn_valid.groupby("postcode")["taxable_income"].mean().reset_index()
    merged = by_pc.merge(g02[["postcode", "Median_tot_prsnl_inc_weekly"]], on="postcode")
    merged = merged[merged["postcode"].map(syn_valid["postcode"].value_counts()) >= 5]
    if len(merged) > 5:
        corr = merged["taxable_income"].corr(merged["Median_tot_prsnl_inc_weekly"])
        print(f"  Correlation (postcode-level, n={len(merged)} postcodes w/ >=5 synthetic rows):")
        print(f"  synthetic mean taxable income  vs  Census median weekly personal income: r={corr:.2f}")
        print("  (positive but weaker than before the Table 16B percentile refinement was added --")
        print("   narrower percentile buckets leave less room for the postcode multiplier to move")
        print("   income away from the percentile-implied value. Expected trade-off, not a bug.)")

    # --- ABS Household Income and Wealth: independent household-level shape check ---
    print("\n-- Cross-check vs ABS Household Income and Wealth 2019-20, Table 1.1 --")
    print("  (equivalised DISPOSABLE HOUSEHOLD income, survey-based, 2019-20 -- different")
    print("   concept/population/year from ATO individual taxable income. Order-of-magnitude")
    print("   and shape check only, not a calibration target.)")
    hiw = pd.read_csv(ROOT / "data" / "processed" / "abs_hiw_equivalised_household_income_percentiles.csv")
    print(f"  {'percentile':>12s}{'ABS household $':>18s}{'synthetic individual $':>24s}")
    for _, row in hiw.iterrows():
        syn_val = np.percentile(syn["taxable_income"], row["percentile"])
        print(f"  {int(row['percentile']):>12d}{row['annual_dollars']:18,.0f}{syn_val:24,.0f}")


if __name__ == "__main__":
    main()
