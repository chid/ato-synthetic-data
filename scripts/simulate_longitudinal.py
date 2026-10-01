"""
Advance the static synthetic population (from generate_synthetic.py) forward year by
year: aging, death, income evolution, new entrants. This turns the t=0 cross-section
into agent-history panel data suitable for a longitudinal/agent-based simulation.

Every mechanism here is one of two kinds -- say which up front so nothing is quietly
overstated:

REAL DATA:
  - Mortality: ABS Life Tables 2021-2023 (Table 9, national), qx by single year of age
    and sex -- an agent's death draw each year is Bernoulli(qx[age, sex]).
  - Aggregate income growth: 4.23% p.a., the average year-over-year growth in mean
    taxable income from ATO Table 1, 2017-18 to 2022-23 (nominal, not inflation-
    adjusted -- there's no separate price-level model here).
  - Target population growth rate: (births - deaths + net overseas migration) /
    national population, from ABS population components (latest rolling year) and the
    Census 2021 national population count.

ASSUMED, DOCUMENTED, TUNABLE (no public data source exists for these -- see
APPROACH.md "Income mobility" section for why):
  - Income mobility: each Taxable agent's income is converted to a percentile rank
    (via ATO Table 16B's curve), blended each year toward a fresh random rank with
    persistence INCOME_RANK_PERSISTENCE (default 0.92), then mapped back to a dollar
    value. This is a mean-reverting rank process, not fit to any transition matrix --
    none exists publicly for Australia (the Productivity Commission's "Fairly equal?"
    report gives only lifetime/qualitative decile-mobility findings from restricted
    HILDA microdata, not an annual matrix). 0.92 is picked to be broadly consistent
    with that report's finding that most people experience decile moves over a
    working life while year-to-year income is still highly persistent -- it is a
    plausibility-checked assumption, not a calibrated one. Change
    INCOME_RANK_PERSISTENCE and re-run to see how much this matters for your use.
  - taxable_status after the income update is redrawn from each income bracket's own
    real P(Taxable) in Table 3A (e.g. only ~31% of $18,201-$25,000 earners are
    actually Taxable, due to LITO/other offsets) rather than a flat tax-free-threshold
    cutoff -- a flat cutoff was tried first and produced an artificial one-off
    reclassification jump in year 1 (~79%->87% Taxable) because plenty of the t=0
    "Non Taxable" population already sits above $18,200. Caught by testing, not by
    reasoning about it in advance.
  - New entrants: sampled (with replacement, with fresh continuous draws) from the
    ORIGINAL t=0 18-29 age slice, not from a real migrant/birth-cohort demographic
    profile. This sidesteps modeling the ~18 year birth-to-workforce lag and actual
    migrant age/sex/origin distributions entirely -- a real simplification, not a
    subtle one.
  - Financial items (salary, deductions, dividends, etc.) are REDRAWN each year from
    Table 3A, using the agent's current sex/taxable_status/income bracket -- not the
    Bernoulli/Gamma draw parameters themselves, which are the same real per-cell rates
    described in generate_synthetic.py. The assumption introduced here is dropping the
    age dimension from that lookup (age x sex x status x bracket cells get suppressed
    too often to stay well-populated for a repeated yearly lookup; sex x status x
    bracket, summed over age, doesn't have that problem) -- a documented trade-off, not
    a silent one. This replaces an earlier, cruder version of this model that just
    froze items at their t=0 values for an agent's entire simulated life, which was
    flagged but not fixed until now.

    Trade-off this introduced, caught by validation: fixing "frozen forever" this way
    means each year's item draw is fresh and independent of the agent's OWN previous
    year, beyond what their current bracket implies. validate_longitudinal.py checks
    corr(an agent's income growth, their salary growth) over 10 years and finds r=0.007
    -- essentially zero. So while item VALUES now correctly track the cross-sectional
    bracket each year (mean deductions rises monotonically with income decile, checked
    in the same script), an individual's own item COMPOSITION has no year-to-year
    persistence -- someone salaried every real year could show a random zero-salary
    year here even with stable circumstances. A more complete fix would give item
    presence its own persistence mechanism (e.g. an AR(1)-style Bernoulli, mirroring
    what INCOME_RANK_PERSISTENCE already does for income); not implemented here --
    flagged as the natural next improvement, not silently left as if items were now
    fully realistic.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import generate_synthetic as gen

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

INCOME_RANK_PERSISTENCE = 0.92
AGGREGATE_INCOME_GROWTH = 0.0423  # ATO Table 1, mean taxable income, 5yr avg YoY
NATIONAL_POPULATION_2021_CENSUS = 25_422_788


def load_life_table():
    df = pd.read_csv(PROCESSED / "abs_life_table_national.csv")
    return {(row.sex, row.age): row.qx for row in df.itertuples()}


def load_growth_rate():
    df = pd.read_csv(PROCESSED / "abs_population_components_latest_year.csv")
    net = df["births"].iloc[0] - df["deaths"].iloc[0] + df["net_overseas_migration"].iloc[0]
    return net / NATIONAL_POPULATION_2021_CENSUS


def load_taxable_probability_by_bracket():
    """P(actually Taxable | in this income bracket), from Table 3A -- real taxable
    status depends on offsets (LITO, SAPTO, etc.), not a flat tax-free-threshold cutoff:
    e.g. only ~31% of people with $18,201-$25,000 income are actually Taxable. Used
    instead of a hard TAX_FREE_THRESHOLD cutoff when re-deriving taxable_status after
    income changes, to avoid an artificial one-off reclassification jump."""
    df = gen.load_table3a()
    g = df.groupby(["income_lo", "income_hi"], dropna=False).apply(
        lambda d: d.loc[d["Taxable status"] == "Taxable", "Individuals | count"].sum() / d["Individuals | count"].sum(),
        include_groups=False,
    )
    lo = np.array([k[0] for k in g.index])
    hi = np.array([np.inf if pd.isna(k[1]) else k[1] for k in g.index])
    order = np.argsort(lo)
    return lo[order], hi[order], g.to_numpy()[order]


def draw_taxable_status(rng, income, bracket_lo, bracket_hi, bracket_p):
    idx = np.clip(np.searchsorted(bracket_lo, income, side="right") - 1, 0, len(bracket_lo) - 1)
    # searchsorted on lo alone can pick a bracket whose hi is already exceeded for very
    # high incomes past the last bracket -- clip to the last (open-ended top) bracket
    p = bracket_p[idx]
    return np.where(rng.random(len(income)) < p, "Taxable", "Non Taxable")


def income_to_rank(sex, income):
    """Interpolate an income value to a continuous 0-100 percentile rank using the
    Table 16B curve for that sex. Values outside the curve's range clip to 1 or 100."""
    curve = gen.load_percentile_curve(sex)
    los = curve["lo"].to_numpy(dtype=float)
    percentiles = np.arange(1, len(curve) + 1)
    return np.clip(np.interp(income, los, percentiles), 1, 100)


def rank_to_income(sex, rank):
    """Map a continuous percentile rank back to a dollar value via smooth (monotonic
    linear) interpolation across Table 16B's 100 published percentile averages.

    Deliberately deterministic given rank, unlike the initial t=0 draw
    (draw_bracket_income), which injects its own within-bucket randomness. That
    randomness is appropriate once, to get a realistic cross-sectional spread from
    only 100 discrete anchor points -- but re-injecting a FRESH stochastic draw every
    single year, independent of the previous year's dollar value, was tried first and
    is a real bug: an agent's rank moves smoothly under the AR(1) copula (rho=0.92
    means a top-bucket earner very likely stays near the top next year), but their
    *dollar* value was being redrawn from scratch each year regardless, including from
    the open-ended top bucket's heavy Pareto tail -- producing wild, uneconomic swings
    (e.g. one simulated year showed +22% mean income driven by a couple of huge
    one-off top-bucket draws). Caught by validation. The trade-off of the deterministic
    fix: everyone landing in the top percentile bucket in a given year gets pushed
    toward that bucket's single published average, so within-top-1%-bucket spread is
    understated during the evolution phase (it's fine at t=0, where the stochastic
    version still runs)."""
    curve = gen.load_percentile_curve(sex)
    percentiles = np.arange(1, len(curve) + 1)
    avg = curve["avg"].to_numpy(dtype=float)
    return np.interp(rank, percentiles, avg)


def rank_ar1_step(rng, ranks, rho):
    """One year of rank-based income mobility, via a Gaussian-copula AR(1): convert
    rank to a standard-normal score (probit), blend z_new = rho*z_old + sqrt(1-rho^2)*
    z_fresh, convert back to a rank via the normal CDF.

    This is NOT the same as linearly blending the ranks themselves
    (new = rho*rank + (1-rho)*fresh) -- that was tried first and is a real bug: linearly
    mixing two Uniform(1,100) variables produces a triangular-shaped result concentrated
    around 50, not a uniform one, so top and bottom earners both get silently dragged
    toward the middle every year. Caught by validation: it showed up as a -7.3% mean-
    income drop in year 1 alone, with no economic mechanism to justify it. The Gaussian-
    copula version preserves the marginal rank distribution as Uniform(1,100) by
    construction, so Corr(z_new, z_old) = rho exactly and the population's income
    cross-section doesn't drift or compress from mobility alone -- only from the
    explicit AGGREGATE_INCOME_GROWTH term."""
    u = np.clip(ranks / 100.0, 1e-4, 1 - 1e-4)
    z_old = norm.ppf(u)
    z_fresh = rng.standard_normal(len(ranks))
    z_new = rho * z_old + np.sqrt(1 - rho**2) * z_fresh
    return np.clip(norm.cdf(z_new) * 100, 1e-2, 100)


def recompute_age_range(age_years):
    bounds = list(gen.AGE_BAND_YEARS.items())
    labels, ranges = zip(*bounds)
    lo = np.array([r[0] for r in ranges])
    out = np.empty(len(age_years), dtype=object)
    for i, age in enumerate(age_years):
        j = np.searchsorted(lo, age, side="right") - 1
        j = min(max(j, 0), len(labels) - 1)
        out[i] = labels[j]
    return out


def advance_one_year(rng, pop, life_table, growth_rate, entrant_pool, year_label, bracket_lo, bracket_hi, bracket_p):
    n = len(pop)

    # 1. mortality
    ages_capped = np.minimum(pop["age_years"].to_numpy(), 100)
    qx = np.array([life_table.get((s, a), 0.5) for s, a in zip(pop["sex"], ages_capped)])
    dies = rng.random(n) < qx
    deaths_this_year = int(dies.sum())
    survivors = pop.loc[~dies].copy()

    # 2. age + age_range
    survivors["age_years"] = survivors["age_years"] + 1
    survivors["age_range"] = recompute_age_range(survivors["age_years"].to_numpy())

    # 3. income mobility (Taxable, known-sex rows only) + aggregate growth (everyone)
    #
    # Table 16B's percentile curve is fixed in 2022-23 dollars. Ranking an income that
    # has already been grown by several years of AGGREGATE_INCOME_GROWTH against that
    # STATIC curve was tried first and is a real bug: prior growth gets misread as
    # "moved up in percentile", the AR(1) step partially locks that inflated rank in
    # (rho=0.92 keeps most of it), rank_to_income then re-anchors the dollar value to
    # that now-too-high rank on the *original* curve, and another year of growth stacks
    # on top -- a compounding feedback loop that produced ~7.5%/year average income
    # growth against a 4.23% target, not caught until validation compared the two. The
    # fix: deflate to 2022-23-equivalent dollars (divide by cumulative growth so far)
    # before ranking, and reinflate by the same cumulative factor after mapping back --
    # so ranking always measures TRUE relative position, independent of how many years
    # of nominal growth have already been applied.
    years_elapsed = year_label - 2023
    growth_factor_before = (1 + AGGREGATE_INCOME_GROWTH) ** (years_elapsed - 1)
    growth_factor_after = (1 + AGGREGATE_INCOME_GROWTH) ** years_elapsed

    is_taxable = (survivors["taxable_status"] == "Taxable") & survivors["sex"].isin(["Male", "Female"])
    for sex in ["Male", "Female"]:
        mask = is_taxable & (survivors["sex"] == sex)
        if not mask.any():
            continue
        deflated = survivors.loc[mask, "taxable_income"].to_numpy() / growth_factor_before
        ranks = income_to_rank(sex, deflated)
        new_ranks = rank_ar1_step(rng, ranks, INCOME_RANK_PERSISTENCE)
        survivors.loc[mask, "taxable_income"] = rank_to_income(sex, new_ranks) * growth_factor_after

    # non-taxable / unknown-sex rows don't go through the rank copula at all -- just
    # carry them forward with the same aggregate nominal growth
    survivors.loc[~is_taxable, "taxable_income"] *= (1 + AGGREGATE_INCOME_GROWTH)

    # Control-total calibration: even with the deflation fix above, the copula step
    # still doesn't hit the target growth rate exactly -- the percentile-interpolation
    # income_to_rank/rank_to_income round trip isn't a perfectly variance-preserving
    # map (our synthetic Male-Taxable population's own rank distribution, at mean 56.4,
    # isn't quite the Uniform(1,100) the copula math assumes; mixing it with genuinely
    # uniform-variance noise shifts the spread, and the income-vs-rank curve is convex,
    # so by Jensen's inequality that spread-shift moves the mean too), and it compounds
    # visibly: measured at 7.5-8.3%/year against the 4.23% target before this fix, not
    # shrinking or drifting further out over 10 years either, so it's a per-step bias,
    # not a one-off transient. Rather than keep chasing the exact statistical source,
    # this rescales the WHOLE taxable population uniformly so realised growth matches
    # the ATO-implied target exactly -- standard "benchmarking to control totals"
    # practice in real government microsimulation models (e.g. STINMOD, TRIM3): the
    # mobility process still decides WHO moves up/down (that's preserved), this only
    # fixes the aggregate LEVEL to match known reality.
    old_mean = pop.loc[~dies, "taxable_income"].mean()
    new_mean = survivors["taxable_income"].mean()
    if new_mean > 0:
        correction = old_mean * (1 + AGGREGATE_INCOME_GROWTH) / new_mean
        survivors["taxable_income"] *= correction
    survivors["taxable_status"] = draw_taxable_status(
        rng, survivors["taxable_income"].to_numpy(), bracket_lo, bracket_hi, bracket_p
    )

    # 3b. redraw financial items (salary, deductions, dividends, etc.) from the agent's
    # NEW sex/status/bracket, instead of freezing them at their t=0 values -- otherwise
    # someone whose income triples over ten years would still show their year-1
    # deduction amounts, which makes no sense once income has moved. Uses Table 3A
    # aggregated over age (see redraw_items_for_income docstring for why age is
    # dropped here) -- a documented simplification, not a silent one.
    item_cols = gen.redraw_items_for_income(
        rng, survivors["sex"].to_numpy(), survivors["taxable_status"].to_numpy(),
        survivors["taxable_income"].to_numpy(),
    )
    for col, values in item_cols.items():
        survivors[col] = values

    # 4. new entrants -- sized to hit the target growth rate on TOTAL population (n),
    # not just to grow the post-mortality survivor count, since deaths already shrank
    # it once this step (missing the "+ deaths_this_year" term here previously caused
    # realised population growth to undershoot the target -- caught by validation)
    n_new = int(round(n * growth_rate)) + deaths_this_year
    if n_new > 0:
        sampled = entrant_pool.sample(n=n_new, replace=True, random_state=rng.integers(0, 2**31)).copy()
        # weighted by the real 18-29 age pyramid (falls back to the latest available
        # year, 2025, for simulated years beyond the data's range) rather than uniform
        sampled["age_years"] = gen.draw_ages_for_sexes(rng, 18, 29, sampled["sex"].to_numpy(), year_label)
        sampled["age_range"] = recompute_age_range(sampled["age_years"].to_numpy())
        sampled["agent_id"] = [f"{year_label}-new-{i}" for i in range(n_new)]
        # entrant_pool holds original 2022-23-dollar incomes -- without this, entrants
        # get relatively poorer every year as the rest of the population's nominal
        # income grows around them and theirs doesn't, dragging the population's
        # realised growth rate below target more each year (part of why growth read
        # ~3.2% against a 4.23% target before this fix)
        sampled["taxable_income"] *= growth_factor_after
        # entrants also carry stale t=0 items (from a different age/income); redraw
        # from their new circumstances for the same reason as survivors above
        entrant_items = gen.redraw_items_for_income(
            rng, sampled["sex"].to_numpy(), sampled["taxable_status"].to_numpy(), sampled["taxable_income"].to_numpy()
        )
        for col, values in entrant_items.items():
            sampled[col] = values
        new_pop = pd.concat([survivors, sampled], ignore_index=True)
    else:
        new_pop = survivors

    stats = {
        "year": year_label,
        "population": len(new_pop),
        "deaths": deaths_this_year,
        "entrants": n_new,
        "mean_age": new_pop["age_years"].mean(),
        "mean_taxable_income": new_pop["taxable_income"].mean(),
        "median_taxable_income": new_pop["taxable_income"].median(),
        "pct_taxable": (new_pop["taxable_status"] == "Taxable").mean() * 100,
    }
    return new_pop, stats


def simulate(n_start: int, n_years: int, seed: int = 42):
    # spawn two independent child streams from one seed, rather than reusing the same
    # seed for both the initial cross-section and the year-over-year evolution -- two
    # np.random.default_rng(42) instances produce correlated draws on their first calls
    # (mortality's first `rng.random(n)` landed suspiciously close to the same stream
    # position as generate()'s first `rng.choice(...)`, undercounting year-1 deaths by
    # ~4 std devs -- caught by validation, not by reasoning about it in advance)
    gen_seed, evo_seed = np.random.SeedSequence(seed).spawn(2)
    rng = np.random.default_rng(evo_seed)
    pop = gen.generate(n_start, seed=gen_seed)
    pop["agent_id"] = [f"t0-{i}" for i in range(len(pop))]
    entrant_pool = pop[pop["age_years"].between(18, 29)].copy()

    life_table = load_life_table()
    growth_rate = load_growth_rate()
    bracket_lo, bracket_hi, bracket_p = load_taxable_probability_by_bracket()
    print(f"Target annual population growth rate (ABS components / Census pop): {growth_rate:.4%}")

    panel_rows = [pop.assign(year=2023)]
    summary_rows = [{
        "year": 2023, "population": len(pop), "deaths": 0, "entrants": 0,
        "mean_age": pop["age_years"].mean(), "mean_taxable_income": pop["taxable_income"].mean(),
        "median_taxable_income": pop["taxable_income"].median(),
        "pct_taxable": (pop["taxable_status"] == "Taxable").mean() * 100,
    }]

    for step in range(1, n_years + 1):
        year_label = 2023 + step
        pop, stats = advance_one_year(
            rng, pop, life_table, growth_rate, entrant_pool, year_label, bracket_lo, bracket_hi, bracket_p
        )
        panel_rows.append(pop.assign(year=year_label))
        summary_rows.append(stats)
        print(f"  {year_label}: pop={stats['population']:,}  deaths={stats['deaths']:,}  "
              f"entrants={stats['entrants']:,}  mean_income=${stats['mean_taxable_income']:,.0f}")

    panel = pd.concat(panel_rows, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    return panel, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20000, help="starting population size")
    ap.add_argument("--years", type=int, default=10, help="number of years to simulate forward")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "synthetic")
    args = ap.parse_args()

    panel, summary = simulate(args.n, args.years, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.out_dir / "longitudinal_panel.csv", index=False)
    summary.to_csv(args.out_dir / "longitudinal_summary_by_year.csv", index=False)
    print(f"\nWrote {len(panel):,} panel rows -> {args.out_dir / 'longitudinal_panel.csv'}")
    print(f"Wrote {len(summary)} year summary -> {args.out_dir / 'longitudinal_summary_by_year.csv'}")


if __name__ == "__main__":
    main()
