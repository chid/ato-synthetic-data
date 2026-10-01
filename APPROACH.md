# Approach write-up: synthetic individual tax records from ATO statistics

These are historical development notes. Raw downloads mentioned below are excluded
from this public copy. Earlier passages describe earlier model versions. See
[README.md](README.md) for current commands and [SOURCES.md](SOURCES.md) for attribution
and a correction to the claimed availability of the 2010-12 AGA mortality table.

Written for critique. Claims below are checked against what's actually in `data/raw/` —
where I'm not sure, I've said so rather than asserted it.

## What was actually downloaded

**ATO Taxation Statistics 2022–23, Individuals** (via data.gov.au, confirmed HTTP 200,
files in `data/raw/`):
- Table 3A — the core table. Sex × taxable status × age range × taxable-income bracket
  (1,322 populated cells), ~80 line items, each as (count, $ total). Covers 16.1M
  individuals — this is every 2022–23 lodger, taxable or not.
- Table 16B — percentile (1–100) medians/averages of taxable income, net tax, total
  income, deductions, by sex. **Now wired into the generator** — see "Method
  improvement: percentile-refined income" below.
- Table 18 (deductions by state/occupation/gender), Table 19 ("100 people" summary),
  Table 1 (aggregates by year) — downloaded but only lightly used so far (extracted to
  CSV, not yet wired into the generator).

**ABS Personal Income in Australia, 2022–23** (via abs.gov.au, confirmed HTTP 200):
- Table 3.1 — national/regional total-income distribution: median, mean, Gini
  coefficient, P80/P20 etc., top 1%/5%/10% shares.
- Table 2.1 — income summary by age group and sex.

**Important correction on scope**: "Personal Income in Australia" is an ABS product, but
it's built from the same underlying *tax and income-support administrative data*
(via the Multi-Agency Data Integration Project), not from the **Census of Population and
Housing**. I did not download Census data. If you need actual Census income/demographic
tables (e.g. `2021 Census - Income and work` — household composition, dwelling type,
income cross-tabbed with education, etc.), that's a separate pull I haven't done.

Practical effect: the ABS table I used is close cousin to the ATO data (same admin
source, broader population including non-lodgers), so it's a decent plausibility check on
personal income figures — but it adds no independent household/demographic signal the way
real Census microdata would.

## Method

1. **Joint demographic draw.** Sample (sex, taxable status, age range, income bracket)
   directly from Table 3A's cell weights (`Individuals | count` normalized to
   probabilities). This is literally the real joint distribution over those four
   dimensions — no modeling assumption here beyond trusting the published counts.

2. **Continuous income within bracket.** Brackets are wide near the top (e.g.
   "$250,001 to $500,000"). Rather than sampling uniformly in the bracket, I solve for a
   power-transform exponent `k` such that `E[lo + (hi-lo)·U^k] = bracket's own published
   mean` (from `Taxable income or loss | dollars / count` for that exact cell). The
   open-ended top bracket ("$1,000,001 or more") uses a Pareto draw with `alpha` solved
   the same way from the cell's published mean.

   *Assumption, not fact*: within a bracket, the true shape is monotonically decreasing
   in most brackets — the power-transform enforces this by construction.

   **Update — now refined with Table 16B.** For Taxable individuals, this bracket is
   further intersected with ATO Table 16B's 100 percentile buckets (by sex) before the
   power transform runs: whichever percentile buckets overlap the Table 3A bracket are
   found, one is picked (uniformly — each percentile is ~1% of the taxable population),
   clipped back into the original bracket, and the power transform/Pareto tail is fit to
   *that bucket's own* published average instead of the whole bracket's. Above ~$150k
   this is a large tightening — e.g. the old top bracket ("$1,000,001 or more", one
   number for everyone above $1M) is now split across percentiles 99 and 100, each with
   its own average. Non Taxable individuals aren't in Table 16B (it's a percentile
   distribution of *taxable* individuals only) and still use the plain bracket draw.

   *Trade-off this introduced, caught by re-running validation*: the postcode-income
   correlation check (below) dropped from r=0.22 to r=0.08. Narrower percentile buckets
   leave less numeric room for the postcode multiplier (step 6) to move income away from
   the percentile-implied value — the postcode signal didn't get worse, it just has less
   space to act in now that the base estimate is tighter. Documented, not silently fixed.

3. **~24 financial items** (salary, interest, dividends franked/unfranked, five
   work-related deduction categories, gifts, total deductions, net rent profit/loss,
   super contributions, capital gains, HELP debt, net tax, Medicare levy): for each,
   presence is `Bernoulli(cell's own count/individuals rate)`, and if present, the dollar
   amount is `Gamma(shape=item-specific constant, mean=cell's own dollars/count)`.

   *Assumption, flagged in code*: the Gamma **shape** parameter per item (e.g. 3.0 for
   salary, 0.7 for unfranked dividends) is a hand-picked guess at how skewed each item's
   distribution is. The source tables give mean, not variance — so the *center* of each
   item's synthetic distribution is real, but the *spread/skew* is invented. I chose
   shapes intuitively (thin-tailed for salary, fat-tailed for capital gains/dividends)
   but haven't validated shape against any external reference.

## What the validation script actually checked (and didn't)

`scripts/validate_synthetic.py` on a 20k-row sample confirmed: sex split within ~1pp,
taxable-status split within ~0.1pp, and for 6 spot-checked items, presence rates within
~0.2pp and mean-when-present within 5–15% of the real Table 3A totals.

It did **not** check:
- Joint/cross-item correlations (e.g. whether people with net rent losses also tend to
  have higher salaries in the synthetic data the way they might in reality) — the model
  has no mechanism to produce these beyond what sharing a demographic cell implies, so
  this is a known, structural gap, not a bug.
- Tail accuracy against ABS's Gini/top-1%-share figures in Table 3.1 — I printed those
  numbers as a side-by-side but never adjusted the generator to match them. Synthetic
  Gini came out ~0.46 on taxable income; I have not compared this to ATO's own Gini for
  taxable-only income (ABS's 0.4-ish figures in Table 3.1 are for *total* income across
  a broader population, so the two Ginis aren't measuring the same population — not a
  clean check).
- ~~Age-within-band shape: ages are drawn uniformly~~ — **fixed, see "Real age pyramid"
  section below.**

## Update: Census data added (sex, industry, state, postcode)

Pulled real ABS Census of Population and Housing 2021 data (General Community Profile
DataPacks, directly downloadable zips — national, state, and **postal area** level) —
this addresses the gap flagged above. Also pulled two more ATO tables to get state and
postcode into the model from the tax side.

**New raw sources** (`data/raw/`):
- `census2021_gcp_aus/`, `census2021_gcp_ste/`, `census2021_gcp_poa/` — genuine Census
  2021 tables at national / state / **postcode (POA)** geography:
  - **G02** — medians & averages (incl. median weekly personal income) per postcode.
  - **G54** — Industry of Employment by Age by Sex, per state.
  - **G01** — total persons by sex, national (used only for one plausibility check).
- `ts23individual05.xlsx` (ATO Table 5) — sex x state x broad industry, ~80 items.
- `ts23individual06.xlsx` (ATO Table 6A) — taxable status x state x SA4 x postcode,
  ~80 items.

**A finding that changed the design**: ATO Table 5's "industry" field only covers
individuals who reported *business* income/expenses — about 1.7M of the 16.1M lodgers
(sole traders), not the general PAYG workforce. Using it to assign "industry" to every
synthetic person would have been wrong — it would describe a business-owner population,
not a typical worker. This is why industry assignment below uses Census G54 (all
employed persons 15+) instead of the ATO table; Table 5 is kept only for the independent
comparison at the bottom of this section.

**What was added to the generator:**
- **State + postcode**: drawn from ATO Table 6A, conditioned on the already-drawn
  taxable status. Real admin data, ~5,266 state/postcode cells.
- **Industry**: drawn from Census G54, conditioned on (sex, state, age band). ATO's
  5-year age ranges don't line up with Census's coarser bands (e.g. Census merges
  25-34 and 35-44 into single bands); each ATO range is mapped to its nearest-overlap
  Census band — a documented approximation (`ATO_AGE_TO_CENSUS_BANDS` in
  `generate_synthetic.py`), not an exact correspondence.
- **Postcode income calibration**: each postcode's Census median *weekly total personal
  income* (G02) is compared to the national median, and the ratio (clipped to
  [0.5, 2.0]) nudges that row's target mean within its ATO income bracket. This mixes
  two different concepts — Census's self-reported weekly personal income across the
  whole population vs ATO's annual taxable income for lodgers — deliberately, as a
  *relative* regional signal only, not an absolute value transfer.

**Validation added** (`scripts/validate_synthetic.py`):
- State and industry draws matched their own source distributions almost exactly, as
  expected (they're literally drawn from those tables — this checks the *sampling
  code*, not the *data's realism*).
- **Independent check**: ATO Table 5 (business-filer industry mix) vs Census G54 (all-
  employee industry mix) turned up real, sensible divergences — e.g. Mining is 1.8% of
  all employees but only 0.1% of business filers (capital-intensive, corporate-run,
  few sole traders), while Professional/Scientific/Technical is 7.8% of employees but
  12.4% of business filers (consultants, tradespeople who invoice as businesses). This
  is genuine signal from combining two independent sources, not noise.
- **Sex ratio**: Census (whole population) is 49.3% male / 50.7% female; the ATO
  taxpayer population is 50.5% male / 49.5% female — a real, sensible divergence
  (children, and some retirees with no lodgment obligation, skew the general population
  more female; the *working, income-earning* population skews slightly more male).
- **Postcode income correlation**: across 1,092 postcodes with ≥5 synthetic rows,
  synthetic mean taxable income correlates with Census median weekly personal income at
  r=0.22 (as first implemented) — positive and in the right direction, but modest. That
  was expected given the calibration only nudges a mean that's still dominated by the
  ATO income bracket the row was drawn into. **This dropped further to r=0.08 once the
  Table 16B percentile refinement below was added** — see that section for why; it's a
  real trade-off from a real improvement, not a regression to fix blindly.

**New limitations this introduces:**
- State/postcode (from ATO Table 6A) and industry (from Census G54) are each drawn
  *independently* conditioned only on their own shared variables — there's no joint
  table saying "this specific postcode has this specific industry mix." A mining town
  postcode in WA will get an industry drawn from WA's *state-wide* industry mix, not
  that town's actual concentration of mining jobs.
- The ATO-age-to-Census-age-band mapping is approximate (documented above); this
  slightly blurs the age-conditioning of the industry draw, mostly around 18-24 and 75+.
- Postcode income calibration mixes two different income concepts (see above) — treat
  it as directional, not a validated absolute adjustment.

## Update: income shape sharpened with Table 16B, plus an ABS household check

Two more changes, prompted by "can you improve this method":

1. **Percentile-refined income** (see updated step 2 above) — the previously-flagged
   "single highest-value improvement" was implemented: Table 16B's 100 percentile
   buckets now narrow the within-bracket draw instead of the raw 28 Table 3A brackets.
   Measured effect on the 20k-row sample (seed 42): p90 moved from 145,367→137,715 and
   p99 from 407,339→414,369 — the *tail* redistributed, since the old $1M+ bracket was
   one blunt number for everyone above $1M and is now split across percentiles 99/100,
   each with its own average. Gini moved from 0.460 to 0.465. Small movements, as
   expected — the mean was already right; this mainly fixes the *shape*, which the old
   validation couldn't even check because it only had 28 numbers to compare against.

2. **Pulled ABS Household Income and Wealth, 2019-20** (`abs_hiw_table1_income_distribution.xlsx`,
   `abs_hiw_table15_income_source.xlsx`) — genuinely new, independent survey data (SIH-
   based, not tax or census admin data). Used one part of it (Table 1.1's P10-P90
   equivalised disposable *household* income) as a further independent validation
   cross-check. **Did not** wire it into the generator itself:
   - Table 1.1 is household-level, equivalised (adjusted for household size), and
     disposable (post-tax/transfer) — three concept mismatches against our
     individual-level, raw, pre-tax taxable income. Forcing it in as a calibration
     input would have papered over those mismatches rather than respecting them.
   - Table 15 (income by main source) is mean-only, household-level, no
     decile/variance breakdown — it doesn't actually solve the "Gamma shapes are
     guessed" problem it was fetched to try to fix. Kept as a downloaded reference,
     not integrated; flagging this rather than forcing a bad fit.
   - The comparison that *did* run is informative on its own: below the median, ABS
     household income exceeds our synthetic individual income (equivalisation lifts
     low-income individuals who live in higher-income households); above the median,
     our individual income overtakes ABS household income (top individual earners
     aren't smoothed down by household-size adjustment, and theirs is pre-tax not
     disposable). Both directions are the expected sign given the concept differences
     — a useful sanity check precisely because the two numbers *shouldn't* match.

## Older weaknesses (still open)

1. **No cross-item correlation model.** Two synthetic individuals in the same
   demographic cell with, say, high salary and high work-related-car-expense are
   independent draws — real taxpayers aren't.
2. **Gamma shapes are still guesses**, not fit to anything real. The ABS Household
   Income pull above was a genuine attempt to fix this and came up short (see above) —
   this remains open. A real fix would need item-level decile/variance data, e.g. from
   ABS SIH microdata/TableBuilder (registration-gated, not a direct download) rather
   than the published summary tables used so far.
3. **356 of 1,322 Table 3A cells have fewer than 20 real individuals** behind them (140
   have fewer than 5) — thin cells are drawn from rarely (weight ∝ size) but are noisy
   in the source when they are.
4. **Only ~24 of ~80 available items implemented** in `ITEMS` (easy to extend).
5. **No household/dwelling/education Census cross-tabs** — the Census pull here is
   scoped to income (G02), industry (G54), and one sex total (G01); if you need
   household composition, dwelling type, or education-by-income, that's a further pull.

## Longitudinal extension: agent-based simulation over time

Requested to support a longitudinal/agent-based simulation, not just a static
cross-section. This turns the t=0 population into a multi-year panel
(`scripts/simulate_longitudinal.py`), and it's the part of this project with the most
genuine trial-and-error, so it's worth walking through what broke and how it was caught
— all via `scripts/validate_longitudinal.py`, none of it caught by reasoning in advance.

**New real data**: ABS Life Tables 2021-2023 (national qx — probability of death — by
single year of age and sex, direct download) and ABS "National, state and territory
population" Table 1 (quarterly births/deaths/net overseas migration, direct download).

**Method**: each simulated year, every agent (1) faces a mortality draw from the life
table and is removed if it hits, (2) ages by one year, (3) has its income evolve, (4)
has taxable_status re-derived from the new income, and (5) new entrants are added to
hit the ABS-implied population growth rate.

**Income evolution is the part with no public data to lean on** (see the "Income
mobility" section above — no direct-download Australian income transition matrix
exists; HILDA microdata is restricted). The mechanism: convert each Taxable agent's
income to a percentile rank against ATO Table 16B's curve, blend it one year forward
via a Gaussian-copula AR(1) process (persistence `INCOME_RANK_PERSISTENCE = 0.92`,
picked to be broadly consistent with the Productivity Commission's qualitative
lifetime-mobility findings, not fit to them), map back to a dollar value, then apply
the ATO-implied aggregate growth trend (4.23% p.a., from Table 1's 5-year average).

**Three real bugs, each only visible once the validation script compared claimed vs.
actual behaviour:**

1. **Correlated RNG streams undercounted year-1 deaths by ~4 standard deviations.**
   `gen.generate(seed=42)` and the outer simulation loop both did
   `np.random.default_rng(42)` — two independently-seeded generators, but seeding two
   generators identically and using them back-to-back for unrelated draws risked
   correlated output on their first calls. Fixed by spawning two child streams from one
   `SeedSequence`. Caught because the validation script computed the life-table-implied
   *expected* death count and it was 125 vs. a realised 81 — a gap large enough
   (p≈0.0005) to be a real bug, not noise, confirmed by empirically resampling the same
   probability vector 2,000 times and finding 81 landed at the 0.05th percentile.

2. **Linearly mixing two `Uniform(1,100)` ranks compresses the distribution.**
   The first mobility implementation did `new_rank = ρ·old_rank + (1-ρ)·fresh_rank`
   with `fresh_rank ~ Uniform(1,100)`. Averaging two uniforms doesn't produce a uniform
   — it produces a triangular-shaped distribution concentrated near the middle. Combined
   with a convex income-vs-rank curve (income grows much faster than linearly for the
   top few percentiles), this quietly dragged high earners toward the middle every year
   more than it pulled low earners up in dollar terms, showing up as a **-7.3% mean-
   income drop in year 1 alone** with no economic story behind it. Fixed by moving the
   mixing into normal-score (probit) space — a standard Gaussian-copula AR(1)
   construction, `z_new = ρ·z_old + √(1-ρ²)·z_fresh` with `z ~ N(0,1)` — which preserves
   the marginal rank distribution by construction.

3. **Ranking against a fixed-dollar curve while income compounds is a feedback loop.**
   Table 16B's percentile curve is fixed in 2022-23 dollars. Once income was several
   years into compounding at 4.23%/year, ranking it against that static curve made
   agents look like they'd moved up in percentile (they hadn't — everyone's nominal
   income had just grown), the AR(1) step partially locked that inflated rank in, and
   mapping back to a dollar value on the same static curve re-anchored them even
   higher — compounding on top of itself. Measured effect: ~7.5-8.3%/year realised
   income growth against a 4.23% target. Partially fixed by deflating income to
   2022-23-equivalent dollars before ranking and reinflating after. This helped but
   didn't fully close the gap (a separate, smaller bias remained — the population's own
   rank distribution wasn't *exactly* `Uniform(1,100)` to begin with, at mean rank 56.4
   not 50.5, and mixing a non-uniform input with genuinely-uniform-variance noise shifts
   the spread, which a convex curve turns into a mean shift too). Rather than keep
   chasing the exact statistical source, **the remaining gap is closed with a control-
   total calibration**: rescale the whole taxable population uniformly each year so
   realised growth matches the ATO-implied target exactly. This is standard practice in
   real government microsimulation models (STINMOD, TRIM3) — the mobility process still
   decides *who* moves up or down; the calibration only fixes the aggregate *level*.
   A related fix in the same family: new entrants were being sampled with their
   original 2022-23-dollar incomes, unadjusted for elapsed time, which made them
   progressively "too poor" relative to the current year and dragged the *reported*
   population mean (which includes entrants) below the calibrated survivor mean —
   fixed by scaling entrant incomes by the same cumulative growth factor.

**Validated result** (20k agents, 10 years, seed 42): population growth 1.545% p.a.
realised vs. 1.545% target (exact, by construction of the entrant-sizing rule);
mortality realised within ordinary sampling noise of the life-table expectation each
year; income growth 3.5%/year realised vs. 4.23% target (see below for why this
residual gap is expected, not a bug); income-rank year-1→2 correlation 0.91-0.92,
matching the 0.92 persistence parameter.

**The remaining ~0.7pp income-growth gap is understood, not patched further**: the
control-total calibration is applied to survivors, but the *reported* population mean
also includes new entrants, who are young (18-29) and so have below-average income by
construction — real economies show exactly this compositional dilution effect (a
population's mean wage grows slower than a fixed cohort's wage, because new, lower-paid
entrants keep joining). Forcing this to exactly 4.23% would mean scaling entrants to
above-average income, which would be the actual fudge.

**What this longitudinal layer does NOT do**, flagged rather than left implicit:
- ~~Only demographics + taxable_status + taxable_income evolve; financial items frozen
  at t=0~~ — **fixed, see "Financial items now evolve" section below** (with a new,
  honestly-documented trade-off of its own).
- New entrants are resampled from the *original* t=0 18-29 age slice, not modeled as
  actual births (which would enter the population ~18 years after birth) or actual
  migrants (who have a different age/industry/country-of-origin profile than the
  existing resident population). This sidesteps two real demographic processes, not
  subtly.
- Mortality uses one *national* life table; no state, socioeconomic, or Indigenous
  mortality differentials, all of which are real and published by the ABS at varying
  levels of aggregation if that granularity matters for your use.
- The Gaussian-copula persistence parameter (0.92) is a plausibility-checked
  assumption, not a calibrated one — there remains no public Australian data to
  calibrate it against (see "Income mobility" above). Change
  `INCOME_RANK_PERSISTENCE` in `scripts/simulate_longitudinal.py` and re-run
  `validate_longitudinal.py` to see how sensitive your use case is to this choice.

## Backtest: build from 2012-13, predict 2022-23, compare to what actually happened

Everything above validates internal consistency — does the model reproduce the data it
was calibrated on, and does the simulation behave the way its own logic intends. None
of that tests whether the *method* has any actual forecasting skill. This does: build a
population using **only** data that genuinely existed as of 2012-13, run it forward 10
years with the same mechanics as `simulate_longitudinal.py`, and compare the resulting
"predicted 2022-23" against the REAL, already-downloaded 2022-23 ATO figures.

**New genuinely old data downloaded** (`data/raw/`, via `scripts/extract_backtest_2012_13.py`):
- `taxstats2013_individual03.xlsx` — the **original** Taxation Statistics 2012-13
  Table 3 (sex × taxable status × age × income bracket, 67 items). This matters: the
  current 2022-23 release's Table 3B *also* has a 2012-13 row (a retrospective
  multi-year compilation done in 2025), but that's not the same as what was actually
  published in 2013-14 — using the original release avoids relying on a retrospective
  restatement.
- `taxstats2013_individual14.xlsx` — the original 2012-13 percentile distribution
  table (100 buckets by sex), letting the backtest reuse the same percentile-refined
  income method as the main model, not a cruder fallback.
- ~~`abs_life_tables_2016_2018.xls`~~ — **superseded.** This was the oldest *ABS* Life
  Table vintage retrievable as a direct download at the time (pre-2016 ABS vintages are
  archived on the deprecated AUSSTATS site behind JS-driven navigation with no
  scrapeable download links, confirmed by a genuine attempt), but using it was a
  look-ahead compromise: a real 2013 forecaster wouldn't have had 2016-2018 outcome
  data. Fixed below.
- `aga_life_table_2010_12_males.xls` / `_females.xls` — **genuinely period-correct.**
  The Australian Government Actuary publishes its own "Australian Life Tables" on the
  same ~5-year, Census-aligned cycle as ABS, as direct-download `.xls` files with no
  archive/JS problem at all (`scripts/extract_period_life_tables.py`). The 2010-12
  vintage is contemporaneous with the 2012-13 backtest. This is a different
  (actuarial, not ABS) source — methodologically close but not identical to ABS's own
  tables — noted as a source-switch, not silently treated as ABS data.

**No-look-ahead trend inputs**, computed from data already on hand but restricted to
years ≤2012-13:
- Income growth: 4.30% p.a. (trailing 5-year average ending 2012-13, from
  `ato_table1_by_year.csv`) — notably close to the 4.23% figure used in the main model
  (computed from 2017-18 to 2022-23), suggesting Australia's nominal wage growth trend
  was similar a decade apart.
- Population growth: 1.70% p.a. ((births − deaths + net overseas migration) for the
  year ending mid-2013, over the ABS "Persons, Australia" total as of June 2013 —
  23,128,129 — both from files already downloaded for the main longitudinal model).

**Result** (`scripts/validate_backtest.py`):

| | t0 synthetic (2012-13) | real 2012-13 |
|---|---|---|
| % taxable | 74.7% | 74.2% |
| % male | 52.4% | 52.2% |

The 2012-13 starting population itself reproduces reality closely — same validation
result as the main model's t0, just on a decade-old vintage.

| | predicted 2022-23 (from 2012-13 + 10y) | real 2022-23 |
|---|---|---|
| % taxable | 76.1% | 78.5% |
| % male | 51.9% | 50.5% |
| mean taxable income | $80,157 | $75,201 |
| median taxable income | $49,158 | $55,961 |

(Numbers above are with the period-correct AGA 2010-12 life table; re-running with the
old 2016-2018 ABS compromise gave +6.9%/-11.3% instead of the +6.6%/-12.2% below — the
mortality-vintage fix barely moves these figures, which is itself informative: mortality
is a second-order effect on income/tax aggregates next to the bracket-creep and
growth-trend issues below.)

Mean income overshoots by +6.6%; median undershoots by -12.2%. **The prediction gets
the aggregate growth roughly right but predicts a more skewed/unequal distribution in
2022-23 than actually happened.** The most likely real cause, not just noise:
`taxable_status`'s bracket-conditional probability (Table 3's own P(Taxable | income
level), which reflects LITO/other offsets — see the "control-total calibration"
section above) was held **fixed at its 2012-13 shape** for the entire 10-year run.
Australia's tax-free threshold, LITO, and offsets like LMITO (2019-2022) genuinely
changed over that decade, generally pushing more low-to-middle earners into
"Taxable" status than the flat 2012-13 rule would predict — this backtest has no
mechanism to reflect real tax policy changes, only demographic and income drift. That's
a real, structural finding about the model's limits, discovered by actually backtesting
it rather than assumed in advance.

**What this backtest does NOT cover** (narrowed scope, for tractability):
- No state/postcode/industry — the original 2012-13 release's postcode table only has
  "top and bottom 10 postcodes," not a full breakdown like the current Table 6A.
- Only ~10 financial items (vs ~24 in the main generator), limited to what the 2012-13
  release's Table 3 contains under directly comparable labels.
- One backtest run (2012-13 → 2022-23, one seed). A rigorous version would run several
  historical starting points to see if the skew-overprediction is a consistent pattern
  or specific to this window — which is exactly what the next section does.

## Second backtest: 2009-10 → 2022-23 (13 years) — does the finding hold up?

Asked directly: is there older ATO data, and is the 2012-13 backtest's finding a
one-off or a real pattern? Data.gov.au's earliest **separately listed** Taxation
Statistics release is 2009-10 (years before that redirect with no distinct dataset —
they may exist as ATO PDF-only publications, not investigated). That release predates
ATO's move to today's tidy long-format tables entirely:

**A genuinely different, harder format.** The 2009-10 release ships as one 82MB zip
containing an old CHM-exported HTML book plus ~180 legacy `.xls` chapter files. The
table we need — **PER11**, "Selected items, by age, sex, taxable status and taxable
income" — is a **cross-tab**: income brackets run across columns, and each age×sex
combination is a stacked block of item rows, with "Non-taxable" folded in as one
column alongside the taxable brackets rather than a separate dimension. Reshaping this
into the same tidy format used elsewhere needed a new parser
(`scripts/extract_backtest_2009_10.py`) that walks the sheet tracking current age/sex
state rather than reading a flat header row.

**A real fidelity reduction, not hidden**: the 2009-10 percentile table (PER9)
publishes only *counts* per percentile bucket, no dollar totals — there's no average
to calibrate a within-bucket power transform against, so this backtest has **no
percentile refinement at all**, just the plain 22-bracket power transform (the method
the main model used *before* Table 16B was added). The joint age×sex×bracket table also
only carries 3 items (Total income, Taxable income, Pension income) — no salary,
deductions, or capital gains at this level for this vintage. And the no-look-ahead
income-growth trend had only 3 usable years (2006-07 to 2009-10; 2004-05 and 2005-06
are `'na'` in ATO's own Table 1 for this item), landing at 3.26% p.a. — noisier than
the 2012-13 backtest's 5-year, 4.30% estimate, and depressed by sitting right after the
2008-09 GFC.

**Mortality**: this backtest also originally used the same 2016-2018 ABS look-ahead
compromise as the 2012-13 backtest. Fixed the same way — the Australian Government
Actuary's "Australian Life Tables 2005-07" vintage, genuinely contemporaneous with
2009-10, downloaded directly with no archive/JS problem
(`scripts/extract_period_life_tables.py`).

**t0 validated well** (`scripts/validate_backtest_2009_10.py`): 73.7% synthetic vs
73.6% real taxable share, 51.6% vs 51.5% male — as tight as every other t0 check in
this project, despite the harder source format.

**The 13-year prediction, though, misses dramatically**:

| | predicted (2009-10 + 13y) | real 2022-23 |
|---|---|---|
| % taxable | 97.6% | 78.5% |
| mean taxable income | $64,407 | $75,201 |
| median taxable income | $52,276 | $55,961 |

**+19.1 percentage points on the taxable share** — far worse than the 2012-13
backtest's ~2.5pp miss, and it's the *same mechanism*, not a new one: Australia's
individual tax-free threshold was **$6,000 in 2009-10**, raised to **$18,200 from
2012-13**. This backtest's `taxable_status` logic holds the 2009-10 bracket structure
(and its $6,000-anchored "Non-taxable" zone) fixed in nominal dollars for the entire
13-year run. As income compounds, more and more people mechanically cross a threshold
that, in nominal terms, never moved — a textbook demonstration of real **bracket creep
/ fiscal drag**, which is precisely the phenomenon that prompted the government to
raise the threshold in reality. The shorter 2012-13 backtest showed a mild version of
the same effect (its $18,200-anchored brackets were still roughly current at the
start); this longer, earlier-starting one shows it starkly. This is consistent evidence
for one real, structural limitation — not two unrelated bugs.

**A second, different miss worth separating out**: mean and median income both
*undershoot* here (-14.4% and -6.6%), unlike the 2012-13 backtest where mean
*overshot*. Likely cause: the 3.26% growth trend was estimated from a short,
GFC-depressed window (2006-07 to 2009-10) that undersold Australia's actual nominal
wage growth over the following 13 years. This is a distinct, additional lesson from
running a second historical window: a short trend-estimation window sitting right
after a recession is a real forecasting risk, independent of the bracket-creep issue.

**What this second backtest does NOT cover** (on top of the first backtest's scope
narrowing): no percentile refinement at all (documented above); only 3 financial items;
the "Non-taxable" bracket bound ($0–$6,000) is an approximation of that era's threshold,
not derived from the source table itself (which doesn't state it numerically); one run,
one seed, same as the first backtest.

## Real age pyramid: replacing uniform-within-band age sampling everywhere

Prompted by "any way to find even better demographic information" — the concrete,
actionable weak point was that every generator in this project (the static model, the
longitudinal evolution's new entrants, and both backtests) drew ages **uniformly**
within each 5-year ATO band. That's wrong in a specific, checkable way: real
populations aren't flat within a band, especially "75 and over" — a genuinely
open-ended band where the population drops off sharply with age due to mortality, not
evenly across 75-95 (the old, arbitrary cap).

**New data**: ABS Table 3101059, "Population - Australia" — real single-year-of-age
population counts by sex, **1971 to present**, direct download
(`scripts/extract_age_pyramid.py`). Being a full historical time series turned out to
be a bonus: the same file supplies period-correct age pyramids for the 2009-10 and
2012-13 backtests as well as the current model, not just one year.

`generate_synthetic.draw_age()` now draws each agent's specific age within their band
weighted by the real population count at each single year of age, for their sex and
(for the two backtests) the correct historical year — not a flat uniform draw. The
same fix was applied to new-entrant age sampling in the longitudinal model and both
backtests (`draw_ages_for_sexes()`), which previously used a flat `Uniform(18,29)`.

**A real, previously-undiscovered bug found while making this fix**: `AGE_BAND_YEARS`
tuples like `"c. 25 - 29": (25, 30)` store `hi` as *exclusive* (the next band's `lo`),
but the original uniform sampler did `rng.integers(lo, hi + 1)`, which treats `hi` as
*inclusive* — so someone in ATO's "25-29" band could be assigned age 30, one year past
the band's real upper edge. This affected every band except the open-ended top one, in
every generator, since the very first version of this project. It's a one-year leak,
easy to miss because it looks like ordinary sampling noise rather than a wrong number —
found only because implementing real weighted sampling required actually reasoning
through what `hi` meant, not because anything downstream visibly broke. Fixed by using
`hi - 1` as the true inclusive max age. The top band's cap was also raised from the old
arbitrary 95 to 100, matching the real pyramid's "100 and over" top code.

**Effect on outputs**: modest and expected, since this changes *within-band* age shape,
not *which* band anyone is in. Synthetic mean age at t0 dropped from a uniform-implied
~85 down to ~80.8 for the 75+ band specifically (real population there is concentrated
near 75, not spread evenly to 95) and overall population mean age shifted slightly
(43.4 vs the low-40s range before). Both backtests' headline findings (skew
over-prediction; bracket-creep-driven taxable-share miss) are unchanged in direction
and roughly unchanged in magnitude — this fix improves demographic realism, it doesn't
touch the income-modelling mechanisms that drove those findings.

## Financial items now evolve with income, instead of being frozen at t=0

Prompted by a generic "improve the approach" — the pick was the longitudinal model's
most prominently and repeatedly flagged "does NOT do": the ~24 financial line items
(salary, deductions, dividends, capital gains, etc.) were drawn once at t=0 and then
carried forward completely unchanged for an agent's entire simulated life, no matter
how much their income moved. Someone whose income tripled over ten years would still
show their year-one deduction amounts. No new data needed for this — it reuses the same
real per-cell Bernoulli/Gamma rates from ATO Table 3A that `generate_synthetic.py`
already draws from at t=0; the fix is calling that same mechanism again each year, with
the agent's *current* bracket.

**Method**: `generate_synthetic.py`'s item-drawing loop was factored out into a reusable
`draw_items()` function. A new `redraw_items_for_income()` looks up each agent's current
(sex, taxable_status, income bracket) — aggregated **over age**, since the full
(age × sex × status × bracket) grid has too many privacy-suppressed gaps to stay
reliable for a lookup run 10+ times per agent — and redraws every item from that cell's
real rates. Applied to both survivors and new entrants each simulated year.

**Validated it actually does what it claims** (`validate_longitudinal.py`):
- **Cross-sectional check** — mean total_deductions by income decile in the final
  simulated year rises monotonically from $846 (bottom decile) to $73,857 (top decile),
  matching the real relationship in Table 3A. This is the core thing being fixed, and it
  works.
- **A genuine new trade-off, not hidden**: fixing "frozen forever" this way means each
  year's draw is fresh and independent of the agent's *own* previous year, beyond what
  their current bracket implies. Checked directly: `corr(an agent's income growth,
  their salary growth)` over the full 10 years comes out at **r=0.007** — essentially
  zero. So item *values* now correctly track the population's cross-sectional
  distribution every year, but an individual's own item *composition* has no year-to-
  year persistence — someone salaried every real year could show a random zero-salary
  year here even with stable personal circumstances. This wasn't obvious from reasoning
  about the fix in advance; it only showed up once the two specific validation checks
  above were run side by side.

**What would close this remaining gap** (not implemented, flagged as the natural next
step): give item *presence* its own persistence mechanism, e.g. an AR(1)-style
correlated Bernoulli draw mirroring what `INCOME_RANK_PERSISTENCE` already does for
income rank — so an agent who has salary income this year is more likely to still have
it next year, rather than each year being an independent coin flip. Not attempted here
to keep this fix scoped to the one problem it targets.

**Not extended to the two backtests** (`backtest_2012_13.py`, `backtest_2009_10.py`) in
this pass — they have their own, smaller item sets already scoped down for tractability,
and their narrative purpose (the bracket-creep and skew-overprediction findings) is
about the income/tax-status mechanism, not item realism. Flagged as a possible follow-up,
not done silently.

## Files

- `data/raw/` — original ATO/ABS/Census files, unmodified (Census as extracted zips).
- `data/processed/` — tidy CSV reshapes (`scripts/extract_ato_data.py`,
  `scripts/extract_census_and_geo_data.py`, `scripts/extract_longitudinal_data.py`,
  `scripts/extract_backtest_2012_13.py`, `scripts/extract_backtest_2009_10.py`,
  `scripts/extract_period_life_tables.py` — period-correct AGA mortality vintages,
  `scripts/extract_age_pyramid.py` — real single-year-of-age population, 1971-present).
- `scripts/generate_synthetic.py` — the static t=0 generator described above.
- `scripts/validate_synthetic.py` — the static-generator comparison checks.
- `scripts/simulate_longitudinal.py` — the year-over-year evolution described above.
- `scripts/validate_longitudinal.py` — the longitudinal comparison checks.
- `scripts/backtest_2012_13.py` / `validate_backtest.py` — the 2012-13→2022-23 backtest.
- `scripts/backtest_2009_10.py` / `validate_backtest_2009_10.py` — the 2009-10→2022-23
  backtest (13 years, cross-tab source format, no percentile refinement).
- `synthetic/synthetic_individuals.csv` — static 20k-row sample output.
- `synthetic/longitudinal_panel.csv` — 10-year agent-history panel (~238k rows).
- `synthetic/longitudinal_summary_by_year.csv` — compact per-year aggregate stats.
- `synthetic/backtest_2012_13_summary_by_year.csv`, `backtest_2012_13_predicted_2022_23.csv`
- `synthetic/backtest_2009_10_summary_by_year.csv`, `backtest_2009_10_predicted_2022_23.csv`
