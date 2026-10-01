"""
Check the longitudinal simulation actually does what its docstring claims: population
growth tracks the ABS-implied rate, deaths track life-table-implied mortality, income
growth compounds near the ATO-implied rate, and the assumed income-rank persistence
comes out close to the INCOME_RANK_PERSISTENCE parameter it was built from.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import generate_synthetic as gen
import simulate_longitudinal as sim

ROOT = Path(__file__).resolve().parent.parent


def main():
    panel_path = ROOT / "synthetic" / "longitudinal_panel.csv"
    if not panel_path.exists():
        panel_path = panel_path.with_suffix(".csv.gz")
    panel = pd.read_csv(panel_path)
    summary = pd.read_csv(ROOT / "synthetic" / "longitudinal_summary_by_year.csv")

    print("=" * 70)
    print("Longitudinal simulation validation")
    print("=" * 70)

    # --- population growth rate ---
    n_years = len(summary) - 1
    realised_cagr = (summary["population"].iloc[-1] / summary["population"].iloc[0]) ** (1 / n_years) - 1
    target = sim.load_growth_rate()
    print(f"\n-- Population growth --")
    print(f"  target (ABS births-deaths+netOSM / Census pop): {target:.4%} p.a.")
    print(f"  realised CAGR over {n_years} years:                {realised_cagr:.4%} p.a.")

    # --- mortality: realised vs life-table-implied ---
    life_table = sim.load_life_table()
    print(f"\n-- Mortality: realised deaths vs life-table-implied expectation --")
    for _, row in panel[panel["year"] < panel["year"].max()].groupby("year"):
        pass
    for year in sorted(panel["year"].unique())[:-1]:
        cohort = panel[panel["year"] == year]
        ages = np.minimum(cohort["age_years"].to_numpy(), 100)
        qx = np.array([life_table.get((s, a), 0.5) for s, a in zip(cohort["sex"], ages)])
        expected_deaths = qx.sum()
        realised_deaths = summary.loc[summary["year"] == year + 1, "deaths"].iloc[0]
        print(f"  {year}->{year+1}: expected {expected_deaths:7.1f}   realised {realised_deaths:5d}")

    # --- income growth ---
    print(f"\n-- Mean taxable income growth vs ATO-implied aggregate trend --")
    print(f"  target: {sim.AGGREGATE_INCOME_GROWTH:.2%} p.a. (nominal, from ATO Table 1)")
    incomes = summary["mean_taxable_income"].to_numpy()
    yoy = incomes[1:] / incomes[:-1] - 1
    print(f"  realised YoY: {np.round(yoy, 4)}")
    print(f"  realised mean YoY: {yoy.mean():.4%}")

    # --- income rank persistence: does the mobility mechanism behave as designed? ---
    print(f"\n-- Income-rank year-over-year autocorrelation vs INCOME_RANK_PERSISTENCE={sim.INCOME_RANK_PERSISTENCE} --")
    p2023 = panel[(panel["year"] == 2023) & (panel["taxable_status"] == "Taxable") & panel["sex"].isin(["Male", "Female"])]
    p2024 = panel[(panel["year"] == 2024)]
    merged = p2023.merge(p2024[["agent_id", "taxable_income"]], on="agent_id", suffixes=("_t0", "_t1"))
    for sex in ["Male", "Female"]:
        sub = merged[merged["sex"] == sex]
        if sub.empty:
            continue
        rank_t0 = sim.income_to_rank(sex, sub["taxable_income_t0"].to_numpy())
        rank_t1 = sim.income_to_rank(sex, sub["taxable_income_t1"].to_numpy())
        corr = np.corrcoef(rank_t0, rank_t1)[0, 1]
        print(f"  {sex}: rank correlation year 1->2, n={len(sub)}: r={corr:.3f}")
    print("  (r should land noticeably below 1.0 -- mobility is happening -- but well")
    print("   above 0, consistent with a persistence parameter this high)")

    # --- age structure ---
    print(f"\n-- Mean age over time (should drift up slightly, tempered by young entrants) --")
    print(summary[["year", "mean_age", "population", "entrants", "deaths"]].to_string(index=False))

    # --- do financial items actually track an agent's changing income now? ---
    print(f"\n-- Item tracking: does salary_or_wages move with an agent's own income change? --")
    print("  (checks the fix for the 'items frozen at t=0' limitation -- if items still")
    print("   just echoed their t=0 value, this correlation would be near 1.0 regardless")
    print("   of how much income changed; if items track income, agents whose income grew")
    print("   a lot should show correspondingly higher salary growth, not a fixed offset)")
    t0 = panel[panel["year"] == 2023][["agent_id", "taxable_income", "salary_or_wages"]]
    tN = panel[panel["year"] == panel["year"].max()][["agent_id", "taxable_income", "salary_or_wages"]]
    merged = t0.merge(tN, on="agent_id", suffixes=("_t0", "_tN"))
    merged = merged[(merged["taxable_income_t0"] > 0) & (merged["salary_or_wages_t0"] > 0)]
    income_growth = merged["taxable_income_tN"] / merged["taxable_income_t0"]
    salary_growth = (merged["salary_or_wages_tN"] + 1) / (merged["salary_or_wages_t0"] + 1)
    corr = np.corrcoef(income_growth, salary_growth)[0, 1]
    print(f"  corr(income growth, salary growth) across {len(merged)} agents who had both "
          f"at t0: r={corr:.3f}")

    # --- cross-sectional sanity: mean item value vs income bracket, in the final year ---
    print(f"\n-- Cross-sectional check, final year: mean deductions should rise with income --")
    final = panel[panel["year"] == panel["year"].max()].copy()
    final["income_decile"] = pd.qcut(final["taxable_income"], 10, labels=False, duplicates="drop")
    by_decile = final.groupby("income_decile").agg(
        mean_income=("taxable_income", "mean"), mean_deductions=("total_deductions", "mean")
    )
    print(by_decile.round(0).to_string())


if __name__ == "__main__":
    main()
