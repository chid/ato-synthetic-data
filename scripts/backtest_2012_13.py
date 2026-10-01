"""
Backtest: build a synthetic population as of the 2012-13 income year using ONLY data
that would genuinely have been available then (the ORIGINAL 2012-13 ATO release, an
older ABS life table vintage, and growth-rate trends computed from years up to and
including 2012-13 only -- no look-ahead), run the same forward-simulation mechanics
used in simulate_longitudinal.py for 10 years, and compare the resulting "predicted
2022-23" population against the REAL, already-downloaded 2022-23 ATO figures.

This is the actual test of whether the modelling approach has any forecasting skill,
as opposed to the internal-consistency checks in validate_longitudinal.py.

Scope, deliberately narrowed (see APPROACH.md for the full reasoning):
  - Mortality uses the 2016-2018 ABS Life Table -- the oldest vintage retrievable as a
    direct download (older ones are archived on a JS-driven legacy site with no
    scrapeable file links). This is a real, small look-ahead compromise: a genuine
    2013 forecaster wouldn't have had 2016-2018 outcome data yet. Documented, not
    hidden.
  - State/postcode/industry are NOT modelled in the backtest (the 2012-13 release's
    postcode table only has "top and bottom 10 postcodes", not a full postcode
    breakdown like the current Table 6A) -- the comparison is scoped to demographics,
    taxable income, and a handful of core financial items.
  - Only ~10 financial items are modelled (vs ~24 in the main generator), limited to
    what the 2012-13 release's Table 3 actually contains under directly comparable
    labels.
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
PROCESSED_BT = ROOT / "data" / "processed" / "backtest_2012_13"
PROCESSED = ROOT / "data" / "processed"

# base name (as extracted from the 2012-13 table) -> (output col, gamma shape)
# shapes reused from generate_synthetic.ITEMS where the underlying item is the same
ITEMS_2013 = {
    "Salary or wages": ("salary_or_wages", 3.0),
    "Gross interest": ("gross_interest", 0.9),
    "Dividends - unfranked amount": ("dividends_unfranked", 0.7),
    "Dividends - franked amount": ("dividends_franked", 0.8),
    "Total Deductions2": ("total_deductions", 1.6),
    "Net rent – profit": ("net_rent_profit", 1.3),
    "Net rent – loss": ("net_rent_loss", 1.3),
    "Net capital gain": ("net_capital_gain", 0.6),
    "Personal superannuation contributions": ("personal_super_contributions", 1.2),
    "Reportable employer superannuation contributions": ("reportable_employer_super", 1.5),
    "Total Income or Loss2": ("total_income", 3.5),
}


def parse_income_range_2013(label):
    """'a. Less than or equal to $6,000' -> (0, 6000); 'd. $18,201 to $25,000' ->
    (18201, 25000); last bracket '$X or more' -> (X, None)."""
    text = label.split(". ", 1)[1] if ". " in label else label
    text = text.replace(",", "").replace("$", "")
    m = re.match(r"Less than or equal to (\d+)", text)
    if m:
        return 0, int(m.group(1))
    m = re.match(r"(\d+) to (\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+) or more", text)
    if m:
        return int(m.group(1)), None
    m = re.match(r"More than (\d+)", text)
    if m:
        return int(m.group(1)), None
    raise ValueError(f"Unparsed 2012-13 income range: {label!r}")


def load_table3_2013():
    df = pd.read_csv(PROCESSED_BT / "table3_2012_13_items_by_bracket.csv")
    for col in df.columns:
        if col.endswith("| count") or col.endswith("| dollars"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    lo_hi = df["Taxable income ranges"].map(parse_income_range_2013)
    df["income_lo"] = [x[0] for x in lo_hi]
    df["income_hi"] = [x[1] for x in lo_hi]
    df["taxable_income_mean"] = df["Taxable income or loss | dollars"] / df[
        "Taxable income or loss | count"
    ].replace(0, np.nan)
    return df


def parse_percentile_range_2013(label):
    text = str(label).replace(",", "")
    m = re.match(r"Less than (\d+)", text)
    if m:
        return 0, int(m.group(1))
    m = re.match(r"(\d+) to (\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+) or more", text)
    if m:
        return int(m.group(1)), None
    raise ValueError(f"Unparsed 2012-13 percentile range: {label!r}")


_PERCENTILE_CACHE_2013 = {}


def load_percentile_curve_2013(sex):
    if sex in _PERCENTILE_CACHE_2013:
        return _PERCENTILE_CACHE_2013[sex]
    df = pd.read_csv(PROCESSED_BT / "table14_2012_13_percentiles.csv")
    df = df[df["sex"] == sex].sort_values("percentile").copy()
    lo_hi = df["ranged_taxable_income"].map(parse_percentile_range_2013)
    df["lo"] = [x[0] for x in lo_hi]
    df["hi"] = [x[1] for x in lo_hi]
    df["avg"] = df["Taxable income or loss $"] / df["Number of individuals no."]
    curve = df[["lo", "hi", "avg"]].reset_index(drop=True)
    _PERCENTILE_CACHE_2013[sex] = curve
    return curve


def income_to_rank_2013(sex, income):
    curve = load_percentile_curve_2013(sex)
    los = curve["lo"].to_numpy(dtype=float)
    percentiles = np.arange(1, len(curve) + 1)
    return np.clip(np.interp(income, los, percentiles), 1, 100)


def rank_to_income_2013(sex, rank):
    curve = load_percentile_curve_2013(sex)
    percentiles = np.arange(1, len(curve) + 1)
    avg = curve["avg"].to_numpy(dtype=float)
    return np.interp(rank, percentiles, avg)


def load_taxable_probability_2013():
    df = load_table3_2013()
    g = df.groupby(["income_lo", "income_hi"], dropna=False).apply(
        lambda d: d.loc[d["Taxable status"] == "Taxable", "Individuals | count"].sum() / d["Individuals | count"].sum(),
        include_groups=False,
    )
    lo = np.array([k[0] for k in g.index])
    hi = np.array([np.inf if pd.isna(k[1]) else k[1] for k in g.index])
    order = np.argsort(lo)
    return lo[order], hi[order], g.to_numpy()[order]


def historical_income_growth_rate():
    """Trailing 5-year average YoY growth in mean taxable income, using ONLY years up
    to and including 2012-13 -- no look-ahead."""
    df = pd.read_csv(PROCESSED / "ato_table1_by_year.csv")
    cols = [c for c in df.columns if "–" in c or "-" in c]
    window = [c for c in cols if c <= "2012–13"][-6:]
    row_no = df[(df["Selected items1"] == "Taxable income or loss2") & (df["Unnamed: 1"] == "no.")]
    row_dollar = df[(df["Selected items1"] == "Taxable income or loss2") & (df["Unnamed: 1"] == "$")]
    means = row_dollar[window].to_numpy(dtype=float)[0] / row_no[window].to_numpy(dtype=float)[0]
    growth = means[1:] / means[:-1] - 1
    return growth.mean()


def historical_population_growth_rate():
    """(births - deaths + net overseas migration) / population, for the year ending
    mid-2013 -- the most recent full year of data a 2013 analyst would have had."""
    comp = pd.read_csv(PROCESSED / "abs_population_components_quarterly.csv")
    comp["quarter"] = pd.to_datetime(comp["quarter"])
    trailing = comp[comp["quarter"] <= "2013-06-01"].tail(4)
    net_flow = (trailing["births"] - trailing["deaths"] + trailing["net_overseas_migration"]).sum() * 1000

    population = pd.read_csv(PROCESSED / "abs_population_total_quarterly.csv")
    pop_2013 = population.loc[population["quarter"] == "2013-06-01", "population"].iloc[0]
    return net_flow / pop_2013


def load_old_life_table():
    """Australian Government Actuary Life Tables 2010-12 -- genuinely contemporaneous
    with 2012-13 (unlike the earlier 2016-2018 ABS vintage compromise; AGA publishes
    its own life tables, methodologically close to ABS's but not identical)."""
    df = pd.read_csv(PROCESSED / "aga_life_table_2010_12.csv")
    return {(row.sex, row.age): row.qx for row in df.itertuples()}


def generate_2013_population(n_rows: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = load_table3_2013()

    weights = np.nan_to_num(df["Individuals | count"].to_numpy(dtype=float))
    weights = weights / weights.sum()
    cell_idx = rng.choice(len(df), size=n_rows, p=weights)
    cells = df.iloc[cell_idx].reset_index(drop=True)

    out = pd.DataFrame({
        "sex": cells["Gender"].to_numpy(),
        "taxable_status": cells["Taxable status"].to_numpy(),
        "age_range": cells["Age"].to_numpy(),
    })
    # 2013 = t0 year, so ages are drawn from the REAL 2013 age pyramid, not today's
    out["age_years"] = [
        gen.draw_age(rng, a, s, 2013)[0] for a, s in zip(out["age_range"], out["sex"])
    ]

    # percentile-refined income, same method as generate_synthetic.py step 2
    taxable_income = np.empty(n_rows)
    is_taxable_sex_known = (out["taxable_status"] == "Taxable") & out["sex"].isin(["Male", "Female"])
    for i in range(n_rows):
        lo, hi, mean = cells["income_lo"].iat[i], cells["income_hi"].iat[i], cells["taxable_income_mean"].iat[i]
        if is_taxable_sex_known.iat[i]:
            sex = out["sex"].iat[i]
            hi_native = None if pd.isna(hi) else hi
            curve = load_percentile_curve_2013(sex)
            hi_eff = hi_native if hi_native is not None else np.inf
            bucket_hi_eff = curve["hi"].fillna(np.inf)
            mask = (bucket_hi_eff > lo) & (curve["lo"] < hi_eff)
            candidates = curve[mask]
            if not candidates.empty:
                row = candidates.iloc[rng.integers(0, len(candidates))]
                clo = max(row["lo"], lo)
                chi = min(row["hi"], hi_eff) if not np.isnan(row["hi"]) else (hi_eff if np.isfinite(hi_eff) else None)
                lo, hi, mean = clo, chi, row["avg"]
        taxable_income[i] = gen.draw_bracket_income(rng, lo, hi, mean, 1)[0]
    out["taxable_income"] = np.round(taxable_income, 2)

    n = len(cells)
    for base, (col, shape) in ITEMS_2013.items():
        count_col, dollar_col = f"{base} | count", f"{base} | dollars"
        if count_col not in cells.columns:
            continue
        counts = cells[count_col].to_numpy(dtype=float)
        dollars = cells[dollar_col].to_numpy(dtype=float)
        individuals = cells["Individuals | count"].to_numpy(dtype=float)
        p_present = np.clip(np.divide(counts, individuals, out=np.zeros(n), where=individuals > 0), 0, 1)
        present = rng.random(n) < np.nan_to_num(p_present)
        mean_amt = np.divide(dollars, counts, out=np.zeros(n), where=counts > 0)
        mean_amt = np.nan_to_num(mean_amt)
        scale = np.divide(np.abs(mean_amt), shape, out=np.zeros(n), where=mean_amt != 0)
        amounts = rng.gamma(shape=shape, scale=np.maximum(scale, 1e-9)) * np.sign(mean_amt)
        out[col] = np.round(np.where(present & (mean_amt != 0), amounts, 0.0), 2)

    return out


def advance_one_year_2013(rng, pop, life_table, growth_rate, entrant_pool, year_label,
                           bracket_lo, bracket_hi, bracket_p, income_growth):
    n = len(pop)
    ages_capped = np.minimum(pop["age_years"].to_numpy(), 100)
    qx = np.array([life_table.get((s, a), 0.5) for s, a in zip(pop["sex"], ages_capped)])
    dies = rng.random(n) < qx
    deaths_this_year = int(dies.sum())
    survivors = pop.loc[~dies].copy()

    survivors["age_years"] = survivors["age_years"] + 1
    survivors["age_range"] = sim.recompute_age_range(survivors["age_years"].to_numpy())

    years_elapsed = year_label - 2013
    gf_before = (1 + income_growth) ** (years_elapsed - 1)
    gf_after = (1 + income_growth) ** years_elapsed

    is_taxable = (survivors["taxable_status"] == "Taxable") & survivors["sex"].isin(["Male", "Female"])
    for sex in ["Male", "Female"]:
        mask = is_taxable & (survivors["sex"] == sex)
        if not mask.any():
            continue
        deflated = survivors.loc[mask, "taxable_income"].to_numpy() / gf_before
        ranks = income_to_rank_2013(sex, deflated)
        new_ranks = sim.rank_ar1_step(rng, ranks, sim.INCOME_RANK_PERSISTENCE)
        survivors.loc[mask, "taxable_income"] = rank_to_income_2013(sex, new_ranks) * gf_after

    survivors.loc[~is_taxable, "taxable_income"] *= (1 + income_growth)

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
        sampled["taxable_income"] *= gf_after
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


def run_backtest(n_start=20000, n_years=10, seed=42):
    rng = np.random.default_rng(seed)
    pop = generate_2013_population(n_start, seed=seed)
    entrant_pool = pop[pop["age_years"].between(18, 29)].copy()

    life_table = load_old_life_table()
    growth_rate = historical_population_growth_rate()
    income_growth = historical_income_growth_rate()
    bracket_lo, bracket_hi, bracket_p = load_taxable_probability_2013()

    print(f"As-of-2012-13 inputs: population growth {growth_rate:.4%} p.a., "
          f"income growth {income_growth:.4%} p.a. (both computed with no look-ahead)")

    summary_rows = [{
        "year": 2013, "population": len(pop), "deaths": 0, "entrants": 0,
        "mean_age": pop["age_years"].mean(), "mean_taxable_income": pop["taxable_income"].mean(),
        "median_taxable_income": pop["taxable_income"].median(),
        "pct_taxable": (pop["taxable_status"] == "Taxable").mean() * 100,
        "sex_male_pct": (pop["sex"] == "Male").mean() * 100,
    }]

    for step in range(1, n_years + 1):
        year_label = 2013 + step
        pop, stats = advance_one_year_2013(
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
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "synthetic")
    args = ap.parse_args()

    final_pop, summary = run_backtest(args.n, args.years, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.out_dir / "backtest_2012_13_summary_by_year.csv", index=False)
    final_pop.to_csv(args.out_dir / "backtest_2012_13_predicted_2022_23.csv", index=False)
    print(f"\nWrote {args.out_dir / 'backtest_2012_13_summary_by_year.csv'}")
    print(f"Wrote {args.out_dir / 'backtest_2012_13_predicted_2022_23.csv'}")


if __name__ == "__main__":
    main()
