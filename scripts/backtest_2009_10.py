"""
Second, longer-horizon backtest: build a population from the ORIGINAL 2009-10 ATO
release (13 years before 2022-23, vs the 10-year 2012-13 backtest) and see whether the
same "predicts a more unequal distribution than actually happened" finding holds at a
longer horizon, or whether it was specific to the 2012-13 window.

Reduced fidelity vs the 2012-13 backtest, and documented as such:
  - No percentile refinement. The 2009-10 percentile table (PER9) only publishes
    counts per percentile bucket, not dollar totals, so there's no average to
    calibrate a within-bucket power transform against. Income is drawn directly from
    PER11's 22 brackets (plus a "Non-taxable" pseudo-bracket) using the plain
    bracket-mean power transform only -- the same method the CURRENT model used
    before the Table 16B refinement was added.
  - Only 3 income-year data points (2006-07 to 2009-10) were available, un-suppressed,
    for the no-look-ahead income growth trend (2004-05 and 2005-06 are 'na' in ATO's
    own Table 1 for this item) -- a shorter, noisier trend estimate than the 2012-13
    backtest's 5-year window.
  - The 2009-10 table only jointly breaks down 3 items by age x sex x bracket (Total
    income, Taxable income, Pension income) -- no salary, deductions, or capital
    gains at this joint level for this vintage.
  - Historical note, not a bug: the individual tax-free threshold was $6,000 in
    2009-10 (raised to $18,200 from 2012-13) -- the "Non-taxable" bracket here is
    treated as [$0, $6,000] to match that era's actual policy, not today's.
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_synthetic as gen
import simulate_longitudinal as sim

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_BT = ROOT / "data" / "processed" / "backtest_2009_10"
PROCESSED = ROOT / "data" / "processed"

ITEMS_2010 = {
    "Total income or loss3": ("total_income", 3.5),
    "Pension income2": ("govt_pensions_allowances", 2.5),
}

ERA_TAX_FREE_THRESHOLD_2009_10 = 6000


def parse_bracket_2010(label):
    if label.startswith("Non-taxable"):
        return 0, ERA_TAX_FREE_THRESHOLD_2009_10
    text = label.replace(",", "").replace("$", "").replace(" ", "")
    m = re.match(r"Lessthan(\d+)", text)
    if m:
        return ERA_TAX_FREE_THRESHOLD_2009_10, int(m.group(1)) - 1
    m = re.match(r"(\d+)-(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+)ormore", text)
    if m:
        return int(m.group(1)), None
    raise ValueError(f"Unparsed 2009-10 bracket: {label!r}")


def load_table_2010():
    df = pd.read_csv(PROCESSED_BT / "per11_2009_10_items_by_bracket.csv")
    lo_hi = df["bracket_raw"].map(parse_bracket_2010)
    df["income_lo"] = [x[0] for x in lo_hi]
    df["income_hi"] = [x[1] for x in lo_hi]
    df["taxable_status"] = np.where(df["bracket_raw"].str.startswith("Non-taxable"), "Non Taxable", "Taxable")
    df["taxable_income_mean"] = df["Taxable income (excluding losses)"] / df["Individuals"].replace(0, np.nan)
    return df


def load_taxable_probability_2010():
    df = load_table_2010()
    g = df.groupby(["income_lo", "income_hi"], dropna=False).apply(
        lambda d: d.loc[d["taxable_status"] == "Taxable", "Individuals"].sum() / d["Individuals"].sum(),
        include_groups=False,
    )
    lo = np.array([k[0] for k in g.index])
    hi = np.array([np.inf if pd.isna(k[1]) else k[1] for k in g.index])
    order = np.argsort(lo)
    return lo[order], hi[order], g.to_numpy()[order]


def historical_income_growth_rate_2010():
    df = pd.read_csv(PROCESSED / "ato_table1_by_year.csv")
    cols = [c for c in df.columns if "–" in c]
    window = [c for c in cols if c <= "2009–10"]
    row_no = df[(df["Selected items1"] == "Taxable income or loss2") & (df["Unnamed: 1"] == "no.")]
    row_dollar = df[(df["Selected items1"] == "Taxable income or loss2") & (df["Unnamed: 1"] == "$")]
    no_vals = pd.to_numeric(row_no[window].iloc[0], errors="coerce")
    dollar_vals = pd.to_numeric(row_dollar[window].iloc[0], errors="coerce")
    means = (dollar_vals / no_vals).dropna().tail(6)
    return means.pct_change().dropna().mean()


def historical_population_growth_rate_2010():
    comp = pd.read_csv(PROCESSED / "abs_population_components_quarterly.csv")
    comp["quarter"] = pd.to_datetime(comp["quarter"])
    trailing = comp[comp["quarter"] <= "2010-06-01"].tail(4)
    net_flow = (trailing["births"] - trailing["deaths"] + trailing["net_overseas_migration"]).sum() * 1000

    population = pd.read_csv(PROCESSED / "abs_population_total_quarterly.csv")
    pop_2010 = population.loc[population["quarter"] == "2010-06-01", "population"].iloc[0]
    return net_flow / pop_2010


def load_old_life_table():
    """Australian Government Actuary Life Tables 2005-07 -- genuinely contemporaneous
    with 2009-10 (replaces the earlier 2016-2018 ABS vintage look-ahead compromise)."""
    df = pd.read_csv(PROCESSED / "aga_life_table_2005_07.csv")
    return {(row.sex, row.age): row.qx for row in df.itertuples()}


def generate_2010_population(n_rows: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = load_table_2010()

    weights = np.nan_to_num(df["Individuals"].to_numpy(dtype=float))
    weights = weights / weights.sum()
    cell_idx = rng.choice(len(df), size=n_rows, p=weights)
    cells = df.iloc[cell_idx].reset_index(drop=True)

    out = pd.DataFrame({
        "sex": cells["sex"].to_numpy(),
        "taxable_status": cells["taxable_status"].to_numpy(),
        "age_range": cells["age_range"].to_numpy(),
    })
    # 2010 = t0 year, so ages are drawn from the REAL 2010 age pyramid, not today's
    out["age_years"] = [
        gen.draw_age(rng, a, s, 2010)[0] for a, s in zip(out["age_range"], out["sex"])
    ]

    taxable_income = np.empty(n_rows)
    for i in range(n_rows):
        lo, hi, mean = cells["income_lo"].iat[i], cells["income_hi"].iat[i], cells["taxable_income_mean"].iat[i]
        taxable_income[i] = gen.draw_bracket_income(rng, lo, hi, mean, 1)[0]
    out["taxable_income"] = np.round(taxable_income, 2)

    n = len(cells)
    for base, (col, shape) in ITEMS_2010.items():
        if base not in cells.columns:
            continue
        dollars = cells[base].to_numpy(dtype=float)
        individuals = cells["Individuals"].to_numpy(dtype=float)
        mean_amt = np.divide(dollars, individuals, out=np.zeros(n), where=individuals > 0)
        # no separate "count with this item" is published here -- treat as always-present
        # with the cell's own average (documented simplification vs the Bernoulli+Gamma
        # approach used elsewhere, which needs a presence RATE this table doesn't have)
        scale = np.divide(np.abs(mean_amt), shape, out=np.zeros(n), where=mean_amt != 0)
        amounts = rng.gamma(shape=shape, scale=np.maximum(scale, 1e-9)) * np.sign(mean_amt)
        out[col] = np.round(amounts, 2)

    return out


def advance_one_year_2010(rng, pop, life_table, growth_rate, entrant_pool, year_label,
                           bracket_lo, bracket_hi, bracket_p, income_growth):
    n = len(pop)
    ages_capped = np.minimum(pop["age_years"].to_numpy(), 100)
    qx = np.array([life_table.get((s, a), 0.5) for s, a in zip(pop["sex"], ages_capped)])
    dies = rng.random(n) < qx
    deaths_this_year = int(dies.sum())
    survivors = pop.loc[~dies].copy()

    survivors["age_years"] = survivors["age_years"] + 1
    survivors["age_range"] = sim.recompute_age_range(survivors["age_years"].to_numpy())

    # no percentile curve for this vintage -- apply aggregate growth + control-total
    # calibration directly, without the rank-copula mobility step. Simpler than the
    # main model, which is itself a documented reduction in fidelity for this backtest.
    survivors["taxable_income"] *= (1 + income_growth)

    old_mean = pop.loc[~dies, "taxable_income"].mean()
    new_mean = survivors["taxable_income"].mean()
    if new_mean > 0:
        survivors["taxable_income"] *= old_mean * (1 + income_growth) / new_mean

    survivors["taxable_status"] = sim.draw_taxable_status(
        rng, survivors["taxable_income"].to_numpy(), bracket_lo, bracket_hi, bracket_p
    )

    n_new = int(round(n * growth_rate)) + deaths_this_year
    if n_new > 0:
        sampled = entrant_pool.sample(n=n_new, replace=True, random_state=rng.integers(0, 2**31)).copy()
        sampled["age_years"] = gen.draw_ages_for_sexes(rng, 18, 29, sampled["sex"].to_numpy(), year_label)
        sampled["age_range"] = sim.recompute_age_range(sampled["age_years"].to_numpy())
        sampled["taxable_income"] *= (1 + income_growth) ** (year_label - 2010)
        new_pop = pd.concat([survivors, sampled], ignore_index=True)
    else:
        new_pop = survivors

    stats = {
        "year": year_label, "population": len(new_pop), "deaths": deaths_this_year, "entrants": n_new,
        "mean_age": new_pop["age_years"].mean(), "mean_taxable_income": new_pop["taxable_income"].mean(),
        "median_taxable_income": new_pop["taxable_income"].median(),
        "pct_taxable": (new_pop["taxable_status"] == "Taxable").mean() * 100,
        "sex_male_pct": (new_pop["sex"] == "Male").mean() * 100,
    }
    return new_pop, stats


def run_backtest(n_start=20000, n_years=13, seed=42):
    rng = np.random.default_rng(seed)
    pop = generate_2010_population(n_start, seed=seed)
    entrant_pool = pop[pop["age_years"].between(18, 29)].copy()

    life_table = load_old_life_table()
    growth_rate = historical_population_growth_rate_2010()
    income_growth = historical_income_growth_rate_2010()
    bracket_lo, bracket_hi, bracket_p = load_taxable_probability_2010()

    print(f"As-of-2009-10 inputs: population growth {growth_rate:.4%} p.a., "
          f"income growth {income_growth:.4%} p.a. (both computed with no look-ahead)")

    summary_rows = [{
        "year": 2010, "population": len(pop), "deaths": 0, "entrants": 0,
        "mean_age": pop["age_years"].mean(), "mean_taxable_income": pop["taxable_income"].mean(),
        "median_taxable_income": pop["taxable_income"].median(),
        "pct_taxable": (pop["taxable_status"] == "Taxable").mean() * 100,
        "sex_male_pct": (pop["sex"] == "Male").mean() * 100,
    }]

    for step in range(1, n_years + 1):
        year_label = 2010 + step
        pop, stats = advance_one_year_2010(
            rng, pop, life_table, growth_rate, entrant_pool, year_label,
            bracket_lo, bracket_hi, bracket_p, income_growth,
        )
        summary_rows.append(stats)
        print(f"  predicted {year_label}: pop={stats['population']:,}  "
              f"mean_income=${stats['mean_taxable_income']:,.0f}  "
              f"median=${stats['median_taxable_income']:,.0f}  "
              f"%taxable={stats['pct_taxable']:.1f}")

    return pop, pd.DataFrame(summary_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--years", type=int, default=13)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "synthetic")
    args = ap.parse_args()

    final_pop, summary = run_backtest(args.n, args.years, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.out_dir / "backtest_2009_10_summary_by_year.csv", index=False)
    final_pop.to_csv(args.out_dir / "backtest_2009_10_predicted_2022_23.csv", index=False)
    print(f"\nWrote {args.out_dir / 'backtest_2009_10_summary_by_year.csv'}")
    print(f"Wrote {args.out_dir / 'backtest_2009_10_predicted_2022_23.csv'}")


if __name__ == "__main__":
    main()
