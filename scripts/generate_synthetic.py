"""
Synthetic individual-taxpayer data generator, calibrated to the real distributions
published in ATO Taxation Statistics 2022-23 (Table 3A) and cross-checked against
ABS Personal Income in Australia 2022-23.

Method
------
1. Demographics (sex, taxable status, age range, taxable income bracket) are drawn
   jointly from the empirical cell weights in Table 3A -- this reproduces the real
   joint distribution across ~1,300 (sex x status x age x income-bracket) cells. The
   specific age *within* that 5-year band is then drawn weighted by ABS's real
   single-year-of-age population counts (Table 3101059) for that sex and year, not
   uniformly -- uniform sampling badly overstates very old ages within "75 and over",
   which drops off sharply due to mortality rather than being flat.

2. Within the drawn income bracket, a continuous taxable income is drawn from a
   distribution bounded by the bracket's published limits, shaped (via a power
   transform, or a Pareto tail for the open-ended top bracket) so that its
   expectation matches the bracket's own published mean (dollars / count from
   Table 3A) -- not just a uniform guess.

   For **Taxable** individuals this bound is first tightened using ATO Table 16B
   (100 percentiles of taxable income, by sex): the Table 3A bracket (up to
   $250,000 wide at the top) is intersected with whichever of the 100 percentile
   buckets for that sex overlap it, one overlapping percentile bucket is picked
   (uniformly -- each represents ~1% of the taxable population), and the power
   transform/Pareto tail is fit to *that* narrower bucket's own published average
   instead of the whole bracket's. This is the single biggest fidelity improvement
   in this file: percentile buckets are far narrower than Table 3A's, especially
   above ~$150k. Table 16B has no Non Taxable population (it excludes them by
   definition), so Non Taxable rows keep the plain bracket-level draw.

3. For each financial line item (salary, interest, dividends, work-related
   deductions, rent, super, etc.), presence is a Bernoulli draw using the item's
   own (count / individuals) rate in that exact demographic cell, and the dollar
   amount -- if present -- is drawn from a Gamma distribution whose mean matches
   the cell's published (dollars / count). Gamma shape is a documented assumption
   per item family (see ITEM_SHAPE below) since the source tables publish only
   counts and totals, not variances.

4. State + postcode are drawn from ATO Table 6A (taxable status x state x SA4 x
   postcode counts), conditioned on the taxable_status already drawn in step 1 --
   this is still ATO admin data, not Census.

5. Industry is drawn from genuine ABS Census 2021 data (Table G54, Industry of
   Employment by Age by Sex, by state) conditioned on (sex, state, census age
   band). This is a deliberate choice over ATO's own Table 5: Table 5's "industry"
   field only covers the ~1.7M individuals who reported business income/expenses
   (sole traders), not the ~10x larger population of ordinary employees, so it
   would badly mis-represent "what industry does this person work in" for most
   rows. Census G54 covers all employed persons 15+, independent of the tax data
   entirely, so this is a real, fit-for-purpose use of Census data, not a
   re-statement of the ATO numbers under another name.

6. Taxable income within the bracket (step 2) is nudged by a Census-derived
   postcode income factor: ABS Census Table G02 publishes each postcode's median
   *weekly total personal income* (a broader, self-reported concept, different
   from *annual taxable income*). The ratio of a postcode's median to the national
   median is used only as a relative regional income-level multiplier on the
   bracket's target mean (clipped to [0.5, 2.0]) -- so someone drawn into an
   expensive-suburb postcode skews toward the upper end of their bracket. This is
   an approximation bridging two different income concepts; see APPROACH.md.

This reproduces marginal and joint-by-bracket distributions closely; it does NOT
reproduce true individual-level correlations beyond what's captured by the shared
bracket/cell conditioning (e.g. someone with high salary in a bracket doesn't
extra-correlate with high dividends beyond both being conditioned on that bracket),
and postcode/industry are each conditionally independent draws given the
demographic fields they share with the core table -- state and industry aren't
correlated with each other beyond both depending on sex.
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

# base item names (as they appear in ato_table3a_items_by_bracket.csv, before " | count"/" | dollars")
# -> (output column name, gamma shape parameter, allow_negative_display)
ITEMS = {
    "Salary or wages": ("salary_or_wages", 3.0),
    "Allowances earnings tips directors fees etc": ("allowances_tips_directors_fees", 1.2),
    "Australian government allowances and payments": ("govt_allowances_payments", 2.0),
    "Australian government pensions and allowances": ("govt_pensions_allowances", 2.5),
    "Gross interest": ("gross_interest", 0.9),
    "Dividends unfranked": ("dividends_unfranked", 0.7),
    "Dividends franked": ("dividends_franked", 0.8),
    "Dividends franking credit": ("dividends_franking_credit", 0.8),
    "Total work related car expenses": ("deduction_car_expenses", 1.8),
    "Work related travel expenses": ("deduction_travel_expenses", 1.2),
    "Total work related uniform/clothing expenses": ("deduction_uniform_expenses", 2.0),
    "Total work related self education expenses": ("deduction_self_education", 1.3),
    "Other work related expenses": ("deduction_other_work_related", 1.4),
    "Total work related expenses": ("deduction_total_work_related", 1.8),
    "Gifts or donations": ("deduction_gifts_donations", 1.0),
    "Total deductions2": ("total_deductions", 1.6),
    "Net rent - profit": ("net_rent_profit", 1.3),
    "Net rent - loss": ("net_rent_loss", 1.3),
    "Total Income or Loss2": ("total_income", 3.5),
    "Reportable employer superannuation contributions": ("reportable_employer_super", 1.5),
    "Personal superannuation contributions": ("personal_super_contributions", 1.2),
    "Capital gains net capital gain": ("net_capital_gain", 0.6),
    "HELP debt balance": ("help_debt_balance", 1.5),
    "Net tax": ("net_tax", 2.5),
    "Total Medicare levy liability": ("medicare_levy", 3.0),
}

AGE_BAND_YEARS = {
    "a. Under 18": (15, 18),
    "b. 18 - 24": (18, 25),
    "c. 25 - 29": (25, 30),
    "d. 30 - 34": (30, 35),
    "e. 35 - 39": (35, 40),
    "f. 40 - 44": (40, 45),
    "g. 45 - 49": (45, 50),
    "h. 50 - 54": (50, 55),
    "i. 55 - 59": (55, 60),
    "j. 60 - 64": (60, 65),
    "k. 65 - 69": (65, 70),
    "l. 70 - 74": (70, 75),
    "m. 75 and over": (75, 101),
}
# NOTE: `hi` in each tuple is the EXCLUSIVE upper bound (i.e. the next band's `lo`) --
# "c. 25 - 29": (25, 30) means ages 25-29 inclusive, matching the ATO label. The very
# last band's hi=101 is set to capture ABS's real single-year-of-age data up to its
# "100 and over" top code (see draw_age), not an arbitrary cutoff like the old (75, 95)
# was -- that arbitrary 95 cap combined with uniform sampling was itself a source of
# unrealistic "very old" ages before the real age-pyramid weighting was added.

# ATO's 5-year age ranges don't line up 1:1 with the Census's coarser bands (which
# start at 15-19 and merge 25-34, 35-44, etc). Approximated by nearest-overlap;
# "under 18" and "18-24" both map onto Census's 15-19/20-24 split imperfectly.
ATO_AGE_TO_CENSUS_BANDS = {
    "a. Under 18": ["15_19"],
    "b. 18 - 24": ["20_24"],
    "c. 25 - 29": ["25_34"],
    "d. 30 - 34": ["25_34"],
    "e. 35 - 39": ["35_44"],
    "f. 40 - 44": ["35_44"],
    "g. 45 - 49": ["45_54"],
    "h. 50 - 54": ["45_54"],
    "i. 55 - 59": ["55_64"],
    "j. 60 - 64": ["55_64"],
    "k. 65 - 69": ["65_74"],
    "l. 70 - 74": ["65_74"],
    "m. 75 and over": ["75_84", "85ov"],
}

NATIONAL_MEDIAN_WEEKLY_INCOME = 805.0  # ABS Census 2021 G02, Australia


def load_table6a_postcodes():
    """ATO Table 6A: taxable status x state x postcode, for assigning geography."""
    df = pd.read_csv(PROCESSED / "ato_table6a_items_by_postcode.csv")
    df = df[["Taxable status", "State/ Territory1", "Postcode", "Individuals | count"]].copy()
    df.columns = ["taxable_status", "state", "postcode_raw", "weight"]
    df = df[df["weight"] > 0]
    is_numeric = df["postcode_raw"].astype(str).str.fullmatch(r"\d+")
    df["postcode"] = np.where(is_numeric, df["postcode_raw"], None)
    return df


def load_census_industry():
    """Census G54: state x sex x census age band x industry, for assigning industry."""
    df = pd.read_csv(PROCESSED / "census_g54_industry_by_age_sex_state.csv")
    return df[df["persons"] > 0]


def load_census_postcode_income():
    df = pd.read_csv(PROCESSED / "census_g02_medians_by_postcode.csv")
    df = df[["postcode", "Median_tot_prsnl_inc_weekly"]].dropna()
    df["postcode"] = df["postcode"].astype(str)
    return dict(zip(df["postcode"], df["Median_tot_prsnl_inc_weekly"]))


def assign_geography(rng, taxable_status_array):
    """Draw (state, postcode) per row, conditioned on taxable_status, from ATO Table 6A."""
    geo = load_table6a_postcodes()
    states = np.empty(len(taxable_status_array), dtype=object)
    postcodes = np.empty(len(taxable_status_array), dtype=object)
    for status in np.unique(taxable_status_array):
        mask = taxable_status_array == status
        sub = geo[geo["taxable_status"] == status]
        p = sub["weight"].to_numpy(dtype=float)
        p = p / p.sum()
        idx = rng.choice(len(sub), size=mask.sum(), p=p)
        states[mask] = sub["state"].to_numpy()[idx]
        postcodes[mask] = sub["postcode"].to_numpy()[idx]
    return states, postcodes


def assign_industry(rng, sex_array, state_array, age_range_array):
    """Draw industry per row from Census G54, conditioned on (sex, state, census age band)."""
    ind = load_census_industry()
    census_age = np.array([ATO_AGE_TO_CENSUS_BANDS[a][0] for a in age_range_array])
    # collapse the two-band "75 and over" case onto its first band for grouping purposes;
    # weights already summed appropriately since we group on the label below
    industries_out = np.empty(len(sex_array), dtype=object)

    key_df = pd.DataFrame({"sex": sex_array, "state": state_array, "age_band_census": census_age})
    for key, group_idx in key_df.groupby(["sex", "state", "age_band_census"]).groups.items():
        sex, state, band = key
        pos = np.asarray(group_idx)
        sub = ind[(ind["sex"] == sex) & (ind["state"] == state) & (ind["age_band_census"] == band)]
        sub = sub.groupby("industry_census_code", as_index=False)["persons"].sum()
        if sub.empty or sub["persons"].sum() == 0:
            industries_out[pos] = "ID_NS"
            continue
        p = sub["persons"].to_numpy(dtype=float)
        p = p / p.sum()
        idx = rng.choice(len(sub), size=len(pos), p=p)
        industries_out[pos] = sub["industry_census_code"].to_numpy()[idx]
    return industries_out


def postcode_income_factor(postcode_array):
    """Ratio of a postcode's Census median weekly personal income to the national
    median, clipped to a sane range. 1.0 (no adjustment) where the postcode has no
    Census match (aggregated 'X other'/'Overseas' rows, or POA code mismatches)."""
    lookup = load_census_postcode_income()
    factors = np.ones(len(postcode_array))
    for i, pc in enumerate(postcode_array):
        med = lookup.get(str(pc))
        if med:
            factors[i] = np.clip(med / NATIONAL_MEDIAN_WEEKLY_INCOME, 0.5, 2.0)
    return factors


def parse_income_range(label):
    """'af. $18,201 to $25,000' -> (18201, 25000); 'aa. $6,000 or less' -> (0, 6000);
    'bl. $1,000,001 or more' -> (1000001, None) open-ended."""
    text = label.split(". ", 1)[1] if ". " in label else label
    text = text.replace(",", "")
    m = re.match(r"\$(\d+) to \$(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"\$(\d+) or less", text)
    if m:
        return 0, int(m.group(1))
    m = re.match(r"\$(\d+) or more", text)
    if m:
        return int(m.group(1)), None
    raise ValueError(f"Unparsed income range: {label!r}")


def load_percentile_curve(sex):
    """ATO Table 16B: 100 percentile buckets of taxable income for `sex`, sorted low to
    high, each with its own published average -- much narrower than Table 3A's 28
    brackets. Only covers Taxable individuals (Table 16 is a percentile distribution of
    *taxable* individuals by definition)."""
    df = pd.read_csv(PROCESSED / "ato_table16b_percentiles.csv")
    df = df[(df["Sex"].str.strip() == sex) & (df["Statistic3"] == "Average")].copy()
    lo_hi = df["Ranged Taxable Income"].map(parse_income_range)
    df["lo"] = [x[0] for x in lo_hi]
    df["hi"] = [x[1] for x in lo_hi]
    df["avg"] = df["Taxable income or loss $"]
    return df.sort_values("Percentile")[["lo", "hi", "avg"]].reset_index(drop=True)


PERCENTILE_CURVES = {}  # lazy cache, keyed by sex


def _percentile_candidates(sex, lo, hi):
    """Percentile buckets for `sex` whose [lo, hi] range overlaps the given bracket."""
    if sex not in PERCENTILE_CURVES:
        PERCENTILE_CURVES[sex] = load_percentile_curve(sex)
    curve = PERCENTILE_CURVES[sex]
    hi_eff = hi if hi is not None and not (isinstance(hi, float) and np.isnan(hi)) else np.inf
    bucket_hi_eff = curve["hi"].fillna(np.inf)
    mask = (bucket_hi_eff > lo) & (curve["lo"] < hi_eff)
    return curve[mask]


def refine_with_percentiles(rng, sex_array, taxable_status_array, lo_array, hi_array, mean_array):
    """For Taxable rows, replace the Table 3A bracket bounds/mean with a narrower,
    randomly-chosen overlapping Table 16B percentile bucket's own bounds/mean, clipped
    back into the original bracket. Non Taxable rows (absent from Table 16B) and any
    bracket with no percentile overlap fall back to the original bracket unchanged."""
    n = len(sex_array)
    out_lo, out_hi, out_mean = np.array(lo_array, dtype=float), np.array(hi_array, dtype=object), np.array(mean_array, dtype=float)

    key_df = pd.DataFrame({"sex": sex_array, "status": taxable_status_array, "lo": lo_array, "hi": [h if h is not None else np.nan for h in hi_array]})
    for key, group_idx in key_df.groupby(["sex", "status", "lo", "hi"], dropna=False).groups.items():
        sex, status, lo, hi = key
        pos = np.asarray(group_idx)
        if status != "Taxable" or sex not in ("Male", "Female"):
            continue
        hi_native = None if (isinstance(hi, float) and np.isnan(hi)) else hi
        candidates = _percentile_candidates(sex, lo, hi_native)
        if candidates.empty:
            continue
        idx = rng.integers(0, len(candidates), size=len(pos))
        chosen = candidates.iloc[idx]
        clo = np.maximum(chosen["lo"].to_numpy(dtype=float), lo)
        hi_eff = hi_native if hi_native is not None else np.inf
        chi_native = chosen["hi"].to_numpy(dtype=float)  # NaN = open-ended percentile (the top one)
        chi = np.minimum(np.where(np.isnan(chi_native), np.inf, chi_native), hi_eff)
        out_lo[pos] = clo
        out_hi[pos] = np.where(np.isinf(chi), None, chi)
        out_mean[pos] = chosen["avg"].to_numpy(dtype=float)
    return out_lo, out_hi, out_mean


def load_table3a():
    df = pd.read_csv(PROCESSED / "ato_table3a_items_by_bracket.csv")
    lo_hi = df["Taxable income range"].map(parse_income_range)
    df["income_lo"] = [x[0] for x in lo_hi]
    df["income_hi"] = [x[1] for x in lo_hi]
    df["taxable_income_mean"] = df["Taxable income or loss2 | dollars"] / df[
        "Taxable income or loss2 | count"
    ].replace(0, np.nan)
    return df


def draw_bracket_income(rng, lo, hi, target_mean, n):
    """Draw n taxable-income values within [lo, hi] (hi=None/NaN => open top bracket),
    shaped so E[X] ~= target_mean using the bracket's own published average."""
    if hi is not None and not (isinstance(hi, float) and np.isnan(hi)):
        span = hi - lo
        if span <= 0 or not np.isfinite(target_mean):
            return np.full(n, lo, dtype=float)
        # X = lo + span * U^k ; E[U^k] = 1/(k+1) for U~Uniform(0,1)
        # solve k from target mean, clipped to sane skew range
        frac = np.clip((target_mean - lo) / span, 0.02, 0.98)
        k = np.clip(1.0 / frac - 1.0, 0.15, 8.0)
        u = rng.random(n)
        return lo + span * (u ** k)
    else:
        # open-ended top bracket: Pareto tail with mean = alpha/(alpha-1) * lo
        if not np.isfinite(target_mean) or target_mean <= lo:
            target_mean = lo * 1.5
        alpha = target_mean / (target_mean - lo)
        alpha = max(alpha, 1.05)
        u = rng.random(n)
        return lo * (1 - u) ** (-1.0 / alpha)


_AGE_PYRAMID = None


def load_age_pyramid():
    """ABS Table 3101059: real single-year-of-age population counts by sex, 1971-2025.
    Used to replace uniform-within-band age sampling -- real ATO age bands aren't flat
    (e.g. "75 and over" drops off sharply with age due to mortality; a uniform draw
    over 75-95 badly overstates the share of very old agents)."""
    global _AGE_PYRAMID
    if _AGE_PYRAMID is None:
        _AGE_PYRAMID = pd.read_csv(PROCESSED / "abs_age_pyramid_by_year.csv")
    return _AGE_PYRAMID


def draw_age(rng, age_label, sex, year, n=1):
    """Draw age(s) within `age_label`'s band, weighted by the real ABS population
    count at each single year of age for that sex and year -- not uniform. Falls back
    to uniform if no matching pyramid data exists for that year (e.g. request outside
    1971-2025) or sex ("All"/unknown).

    A real off-by-one bug lived here before the age-pyramid rewrite: AGE_BAND_YEARS'
    `hi` is exclusive (the next band's `lo`), but the original uniform sampler did
    `rng.integers(lo, hi + 1)`, treating `hi` as inclusive -- so e.g. someone in ATO's
    "25-29" band could be assigned age 30, one year into the next band. Every band
    except the open-ended top one had this leak. Fixed here by using `hi - 1` as the
    true inclusive max age."""
    lo, hi = AGE_BAND_YEARS[age_label]
    max_age = hi - 1
    pyramid = load_age_pyramid()
    available_years = pyramid["year"].unique()
    use_year = year if year in available_years else min(available_years, key=lambda y: abs(y - year))
    sub = pyramid[(pyramid["sex"] == sex) & (pyramid["year"] == use_year) & pyramid["age"].between(lo, max_age)]
    if sub.empty or sub["population"].sum() == 0:
        return rng.integers(lo, hi, size=n)
    p = sub["population"].to_numpy(dtype=float)
    p = p / p.sum()
    return rng.choice(sub["age"].to_numpy(), size=n, p=p)


def draw_ages_for_sexes(rng, lo, hi, sexes, year):
    """Vectorized draw_age for a mixed-sex array (e.g. new entrants) -- weighted by the
    real age pyramid for [lo, hi] rather than uniform, same rationale as draw_age."""
    pyramid = load_age_pyramid()
    available_years = pyramid["year"].unique()
    use_year = year if year in available_years else min(available_years, key=lambda y: abs(y - year))
    out = np.empty(len(sexes), dtype=int)
    for sex in np.unique(sexes):
        mask = sexes == sex
        sub = pyramid[(pyramid["sex"] == sex) & (pyramid["year"] == use_year) & pyramid["age"].between(lo, hi)]
        if sub.empty or sub["population"].sum() == 0:
            out[mask] = rng.integers(lo, hi + 1, size=mask.sum())
        else:
            p = sub["population"].to_numpy(dtype=float)
            p = p / p.sum()
            out[mask] = rng.choice(sub["age"].to_numpy(), size=mask.sum(), p=p)
    return out


def generate(n_rows: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = load_table3a()

    weights = df["Individuals | count"].to_numpy(dtype=float)
    weights = weights / weights.sum()
    cell_idx = rng.choice(len(df), size=n_rows, p=weights)

    cells = df.iloc[cell_idx].reset_index(drop=True)

    out = pd.DataFrame(
        {
            "sex": cells["Sex4"].to_numpy(),
            "taxable_status": cells["Taxable status"].to_numpy(),
            "age_range": cells["Age range3"].to_numpy(),
            "taxable_income_bracket": cells["Taxable income range"].to_numpy(),
        }
    )
    out["age_years"] = [
        draw_age(rng, a, s, 2023)[0] for a, s in zip(out["age_range"], out["sex"])
    ]

    state, postcode = assign_geography(rng, out["taxable_status"].to_numpy())
    out["state"] = state
    out["postcode"] = postcode
    out["industry"] = assign_industry(rng, out["sex"].to_numpy(), state, out["age_range"].to_numpy())

    refined_lo, refined_hi, refined_mean = refine_with_percentiles(
        rng,
        cells["Sex4"].to_numpy(),
        cells["Taxable status"].to_numpy(),
        cells["income_lo"].to_numpy(),
        cells["income_hi"].to_numpy(),
        cells["taxable_income_mean"].to_numpy(dtype=float),
    )

    income_factor = postcode_income_factor(postcode)
    adjusted_mean = refined_mean * income_factor

    taxable_income = np.empty(n_rows)
    for i in range(n_rows):
        taxable_income[i] = draw_bracket_income(rng, refined_lo[i], refined_hi[i], adjusted_mean[i], 1)[0]
    out["taxable_income"] = np.round(taxable_income, 2)

    for col, values in draw_items(rng, cells).items():
        out[col] = values

    return out


def draw_items(rng, cells):
    """The Bernoulli(presence)+Gamma(amount) item draw, factored out of generate() so
    it can also be called from the longitudinal simulation to REDRAW items each year
    from an agent's current bracket, instead of freezing them at their t=0 values."""
    n = len(cells)
    out = {}
    for base, (col, shape) in ITEMS.items():
        count_col = f"{base} | count"
        dollar_col = f"{base} | dollars"
        if count_col not in cells.columns:
            continue
        counts = cells[count_col].to_numpy(dtype=float)
        dollars = cells[dollar_col].to_numpy(dtype=float)
        individuals = cells["Individuals | count"].to_numpy(dtype=float)

        p_present = np.divide(counts, individuals, out=np.zeros(n), where=individuals > 0)
        p_present = np.clip(np.nan_to_num(p_present), 0, 1)
        present = rng.random(n) < p_present

        mean_amt = np.divide(dollars, counts, out=np.zeros(n), where=counts > 0)
        mean_amt = np.nan_to_num(mean_amt)
        scale = np.divide(mean_amt, shape, out=np.zeros(n), where=mean_amt > 0)
        amounts = rng.gamma(shape=shape, scale=np.maximum(scale, 1e-9))
        amounts = np.where(present & (mean_amt > 0), amounts, 0.0)
        out[col] = np.round(amounts, 2)
    return out


_TABLE3A_BY_BRACKET = None


def load_table3a_by_sex_status_bracket():
    """Table 3A aggregated over age range, to (sex, taxable status, income bracket) --
    used to redraw an agent's financial items each simulated year from their CURRENT
    bracket. Dropping the age dimension is a deliberate simplification: it keeps every
    (sex, status, bracket) cell well-populated (no privacy-suppressed gaps to patch
    over), at the cost of losing age-specific item rates within a bracket -- documented
    in APPROACH.md, not silent."""
    global _TABLE3A_BY_BRACKET
    if _TABLE3A_BY_BRACKET is None:
        df = load_table3a()
        item_cols = [c for c in df.columns if c.endswith("| count") or c.endswith("| dollars")]
        agg = df.groupby(["Sex4", "Taxable status", "Taxable income range"], as_index=False)[
            ["income_lo", "income_hi"] + item_cols
        ].agg({**{c: "sum" for c in item_cols}, "income_lo": "first", "income_hi": "first"})
        _TABLE3A_BY_BRACKET = agg
    return _TABLE3A_BY_BRACKET


def redraw_items_for_income(rng, sex_array, taxable_status_array, income_array):
    """Given each agent's CURRENT sex/taxable_status/income, look up the matching
    (sex, status, bracket) cell in Table 3A and redraw their financial items from it --
    so a promoted/demoted agent's deductions etc. track their new circumstances instead
    of staying frozen at whatever they were assigned at t=0."""
    agg = load_table3a_by_sex_status_bracket()
    n = len(sex_array)
    out_cols = {col: np.zeros(n) for _, (col, _) in ITEMS.items()}

    for (sex, status), group_idx in pd.DataFrame(
        {"sex": sex_array, "status": taxable_status_array}
    ).groupby(["sex", "status"]).groups.items():
        pos = np.asarray(group_idx)
        sub = agg[(agg["Sex4"] == sex) & (agg["Taxable status"] == status)].sort_values("income_lo")
        if sub.empty:
            continue
        lo = sub["income_lo"].to_numpy(dtype=float)
        idx = np.clip(np.searchsorted(lo, income_array[pos], side="right") - 1, 0, len(sub) - 1)
        cells = sub.iloc[idx].reset_index(drop=True)
        for col, values in draw_items(rng, cells).items():
            out_cols[col][pos] = values
    return out_cols


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20000, help="number of synthetic individuals")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--out", type=Path, default=ROOT / "synthetic" / "synthetic_individuals.csv"
    )
    args = ap.parse_args()

    df = generate(args.n, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} synthetic rows -> {args.out}")


if __name__ == "__main__":
    main()
