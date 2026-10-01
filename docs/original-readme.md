# ATO statistics — data copy + synthetic generator

Historical workflow notes, preserved from the original workspace. File paths below
are relative to the repository root. Raw downloads are excluded from this public
copy. See the [current README](../README.md) and [source date correction](../SOURCES.md#backtest-source-date-correction).

## Sources (raw copies in `data/raw/`)

**ATO Taxation Statistics 2022–23, Individuals** (data.gov.au):
- `ts23individual03.xlsx` — Table 3A: ~80 income/deduction/offset items x count & $, broken
  down by sex x taxable status x age range x taxable income bracket (1,322 cells, 16.1M
  individuals). This is the core joint-distribution table the generator is calibrated on.
- `ts23individual16.xlsx` — Table 16: percentile distribution (1–100) of taxable income,
  net tax, total income, deductions, etc., by sex.
- `ts23individual18.xlsx` — Table 18: deductions by state/occupation/gender.
- `ts23individual19.xlsx` — Table 19: "if Australia was 100 people" summary.
- `ts23individual01.xlsx` — Table 1: individuals key aggregates, 2000–01 to 2022–23.

**ABS Personal Income in Australia, 2022–23** (abs.gov.au), used to sanity-check the ATO
figures against a broader population (includes non-lodgers):
- `abs_table3_distribution.xlsx` — Table 3: income distribution, Gini coefficient,
  percentile ratios (P80/P20 etc.), by region.
- `abs_table2_age_sex.xlsx` — Table 2: income summary stats by age group and sex.

**More ATO tables** (state/postcode/industry, admin tax data):
- `ts23individual05.xlsx` — Table 5: sex x state x broad industry, ~80 items.
  Scope caveat: only covers the ~1.7M lodgers with business income (sole traders),
  not the general workforce — see APPROACH.md.
- `ts23individual06.xlsx` — Table 6A: taxable status x state x SA4 x postcode, ~80 items.

**ABS Census of Population and Housing 2021** (abs.gov.au datapacks) — genuine,
independent (non-tax) survey data, downloaded at national/state/postcode geography:
- `census2021_gcp_aus/`, `census2021_gcp_ste/`, `census2021_gcp_poa/` — General
  Community Profile DataPacks containing (among ~240 tables each) G02 (medians &
  averages incl. median personal income), G54 (industry of employment by age by sex),
  G01 (basic person counts by sex).

**ABS Household Income and Wealth, 2019–20** (abs.gov.au) — independent SIH survey data,
used as a further validation cross-check (see APPROACH.md for why it wasn't wired into
the generator itself — household/equivalised/disposable income is a different concept
from ATO's individual/raw/pre-tax taxable income):
- `abs_hiw_table1_income_distribution.xlsx` — Table 1: equivalised disposable household
  income percentiles (P10–P90), quintile means, Gini.
- `abs_hiw_table15_income_source.xlsx` — Table 15: household income by main source
  (employee, business, investment, super, government) — mean-only, downloaded as
  reference but not integrated (no decile/variance breakdown, so it doesn't solve the
  "Gamma shapes are guessed" problem it was fetched for).

## Processed copies (`data/processed/*.csv`)

Straight tidy reshapes of the above — one row per real table row, human-readable column
names. Regenerate with:

```
source .venv/bin/activate
python3 scripts/extract_ato_data.py
python3 scripts/extract_census_and_geo_data.py
```

## Synthetic data generator (`scripts/generate_synthetic.py`)

Generates individual-level synthetic tax records that reproduce the real distributions:

```
source .venv/bin/activate
python3 scripts/generate_synthetic.py --n 20000 --seed 42 --out synthetic/synthetic_individuals.csv
```

**Method:**
1. Demographics (sex, taxable status, age range, taxable-income bracket) are drawn jointly
   from the real cell weights in Table 3A — reproduces the true joint distribution across
   ~1,300 cells.
2. Continuous taxable income within the drawn bracket is shaped (power transform, or a
   Pareto tail for the open-ended top bracket) so its expectation matches that bracket's
   own published mean, not just a uniform guess. For **Taxable** individuals, the
   bracket is first narrowed further using ATO Table 16B's 100 percentile buckets (by
   sex) — a big fidelity gain above ~$150k, where Table 3A's brackets get very wide.
3. ~24 financial line items (salary, interest, dividends, work-related deduction
   categories, rent, super contributions, capital gains, etc.) are each drawn as:
   Bernoulli(presence) using the item's real (count / individuals) rate in that exact
   cell, then Gamma(mean = cell's published dollars/count) if present. Gamma shape per
   item is a documented, tunable assumption (`ITEMS` dict in the script) since the source
   tables publish counts and totals but not variances.
4. **State + postcode** drawn from ATO Table 6A, conditioned on taxable status.
5. **Industry** drawn from genuine Census G54 data, conditioned on (sex, state, age
   band) — deliberately not from ATO's own Table 5, which only covers business-income
   filers (see APPROACH.md for why that would have been the wrong source).
6. **Postcode income calibration**: nudges each row's target income mean by its
   postcode's Census median-income ratio to the national median (clipped to
   [0.5, 2.0]) — a directional regional adjustment, not an exact transfer (Census
   income is weekly/self-reported/whole-population; ATO income is annual/taxable/
   lodgers-only).

This matches marginals and per-bracket conditional distributions closely (see validation
below); it does not fabricate individual-level correlations beyond what sharing a bracket
already implies, and state/industry are drawn independently of each other beyond sharing
sex — there's no joint table saying a specific postcode has a specific industry mix.

## Validation

```
python3 scripts/validate_synthetic.py
```

Compares the synthetic sample's mean/percentiles/Gini, sex & taxable-status splits,
per-item presence-rate & mean-when-present, state split, and industry split against the
real ATO/Census tables they were drawn from — plus two genuinely independent
cross-checks: ATO business-filer industry mix vs Census all-employee industry mix (real,
sensible divergences, e.g. Mining is corporate-heavy so under-represented among business
filers), and ATO taxpayer sex ratio vs Census whole-population sex ratio (taxpayers skew
slightly more male than the general population). On a 20k-row sample: sex split within
~1pp, taxable status within ~0.1pp, item presence rates within ~0.2pp, item means within
~5–15%, state/industry splits within ~1pp of their own source (expected, since drawn
directly from it), and postcode-level income correlates with Census median income at
r≈0.08 (positive, right direction, weaker after the Table 16B refinement narrowed the
room for that adjustment — see APPROACH.md). Also cross-checked against ABS Household
Income and Wealth's household income percentiles — diverges in the expected direction
(household equivalisation lifts the bottom, individual pre-tax income overtakes at the
top), which is itself a useful sanity check.

## Longitudinal / agent-based simulation (`scripts/simulate_longitudinal.py`)

Advances the static population forward year by year — aging, death, income evolution,
new entrants — producing a multi-year agent-history panel:

```
source .venv/bin/activate
python3 scripts/extract_longitudinal_data.py   # one-off: pulls ABS Life Tables + population components
python3 scripts/simulate_longitudinal.py --n 20000 --years 10 --seed 42
python3 scripts/validate_longitudinal.py
```

**Method**: real ABS Life Table mortality by age/sex; real ABS-implied population
growth rate for new entrants; income evolves via a Gaussian-copula rank-persistence
process (ρ=0.92, a documented assumption — no public Australian income-transition-
matrix data exists) plus the ATO-implied 4.23%/year aggregate growth trend, with the
population rescaled each year to hit that target exactly (standard "control-total
calibration," as used in real microsimulation models like STINMOD/TRIM3) since the
copula mechanism alone didn't hit it precisely.

This module went through three real, validation-caught bugs before landing at the
above — correlated RNG streams undercounting year-1 deaths, a naive linear rank-mixing
scheme that silently compressed the income distribution (-7.3% mean income in year 1
alone, for no economic reason), and a compounding feedback loop from ranking
already-grown income against a fixed-dollar percentile curve. All three, plus what the
final validated numbers look like, are written up in detail in APPROACH.md — read that
before trusting or extending this module further.

**What it does NOT do**: evolve the ~24 static financial line items (deductions,
dividends, etc. stay frozen per-agent), model true birth-to-workforce or migrant
demographic profiles for new entrants (they're resampled from the original 18-29
cohort), or use anything but one national life table (no state/socioeconomic
mortality differentials).

## Backtest: build from 2012-13, predict 2022-23 (`scripts/backtest_2012_13.py`)

The one part of this project that tests actual forecasting skill rather than internal
consistency. Downloads the **original** 2012-13 ATO release (not a retrospective
compilation) and a genuinely period-correct mortality table, builds a population using
only what would have been knowable in 2013, and simulates it forward 10 years to
compare against the REAL 2022-23 figures already in this repo:

```
source .venv/bin/activate
python3 scripts/extract_backtest_2012_13.py
python3 scripts/extract_period_life_tables.py   # AGA Life Tables 2005-07 & 2010-12
python3 scripts/backtest_2012_13.py --n 20000 --years 10 --seed 42
python3 scripts/validate_backtest.py
```

Mortality uses the Australian Government Actuary's "Australian Life Tables 2010-12" —
genuinely contemporaneous with 2012-13, not the 2016-2018 ABS vintage this originally
used as a documented look-ahead compromise (pre-2016 ABS vintages are archived behind
JS navigation with no scrapeable download links; AGA publishes the same kind of table
on the same cycle with plain direct downloads — see APPROACH.md for the full story).

**Result**: the 2012-13 starting population matches real 2012-13 stats closely (same
quality as the main model's t0). The 10-year-forward prediction gets aggregate growth
roughly right but overshoots mean income by +6.6% while undershooting median income by
-12.2% — it predicts a **more unequal 2022-23 than actually happened**. The likely real
cause: taxable-status probability by income bracket was held fixed at its 2012-13 shape
for 10 years, but Australia's tax-free threshold and offsets (LITO, LMITO) genuinely
changed over that decade. Full detail is in APPROACH.md.

## Second backtest: 2009-10, 13 years (`scripts/backtest_2009_10.py`)

A longer-horizon check using data.gov.au's earliest separately-listed ATO release
(2009-10 — a genuinely harder source: an old CHM-book zip with cross-tab `.xls`
tables, no percentile-refinement data available at all):

```
python3 scripts/extract_backtest_2009_10.py
python3 scripts/extract_period_life_tables.py   # if not already run above
python3 scripts/backtest_2009_10.py --n 20000 --years 13 --seed 42
python3 scripts/validate_backtest_2009_10.py
```

Mortality uses AGA's "Australian Life Tables 2005-07" — contemporaneous with 2009-10.

**Result**: t0 validates as tightly as everywhere else (73.7% vs 73.6% real taxable
share). The 13-year prediction misses the taxable share by **+19.1 percentage points**
(97.6% predicted vs 78.5% real) — far worse than the first backtest, and for the same
reason at higher dose: the 2009-10 tax-free threshold was $6,000 (raised to $18,200
from 2012-13), held fixed in nominal dollars for 13 years of compounding income —
textbook **bracket creep**, the exact phenomenon that prompted the real threshold
increase. A second, separate lesson: mean and median income both *undershoot* here
(opposite sign to the first backtest), traced to a short, GFC-depressed 3-year growth-
trend estimate. Two backtests, two different real lessons about the model's limits —
detail in APPROACH.md.

## Real age pyramid (`scripts/extract_age_pyramid.py`)

Every generator in this project (static model, longitudinal entrants, both backtests)
used to draw ages **uniformly** within each 5-year ATO band — wrong for "75 and over"
in particular, where the real population drops off sharply with age. Fixed using ABS
Table 3101059 (real single-year-of-age population by sex, 1971-present, direct
download), which as a bonus supplies period-correct pyramids for both backtest years
too, not just the current model:

```
python3 scripts/extract_age_pyramid.py
```

Run this once — `generate_synthetic.py`, `simulate_longitudinal.py`, and both backtest
scripts all pick it up automatically. **Found a real, previously-undiscovered off-by-one
bug in the process**: age bands were being sampled one year too wide (e.g. "25-29"
could produce age 30) since the very first version of this project — `hi` in
`AGE_BAND_YEARS` is exclusive, but the old sampler treated it as inclusive. Fixed
alongside the pyramid change. Detail, including the effect on outputs (modest, as
expected — this changes age *shape* within a band, not *which* band anyone is in), is
in APPROACH.md.

## Financial items now evolve with income

The longitudinal model's most-flagged limitation: the ~24 financial items (salary,
deductions, dividends, etc.) used to be drawn once at t=0 and frozen for an agent's
entire simulated life, no matter how much their income changed. Fixed by redrawing
items every year from the agent's *current* bracket, reusing the same real Table 3A
rates `generate_synthetic.py` already uses — no new data needed, just calling the same
mechanism again each year (`generate_synthetic.redraw_items_for_income`).

Validated both ways: mean deductions now rises monotonically with income decile in any
given year (the thing being fixed), **but** an individual agent's own income growth and
salary growth over 10 years correlate at only r=0.007 — fixing "frozen forever" traded
it for "no year-to-year persistence in which items a person has." Both results, and what
a more complete fix would need (item-presence persistence, not implemented), are in
APPROACH.md. Not extended to the two backtests in this pass.

## Extending

- Add more items to `ITEMS` in `generate_synthetic.py` — any of the ~80 columns in
  `ato_table3a_items_by_bracket.csv` can be wired in the same way.
- Increase `--n` for a larger synthetic population (linear runtime).
- Add a joint postcode×industry table (not currently available from a single source at
  this geography) if the "no correlation between the two" limitation matters for your use.
- Pull Census household/dwelling/education tables if you need those cross-tabs too.
- Fix the Gamma-shape guesses properly: needs item-level decile/variance data, which
  means ABS SIH microdata/TableBuilder (registration-gated) — the publicly downloadable
  ABS Household Income and Wealth summary tables turned out to be mean-only and the
  wrong grain for this (see APPROACH.md).
