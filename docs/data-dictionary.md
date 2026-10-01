# Data dictionary

The main `synthetic/synthetic_individuals.csv` sample has the columns below. Categories follow the source table labels. Dollar values are simulated and rounded to cents. Zero usually means an item was absent in the synthetic draw.

## Demographics and geography

| Column | Meaning |
| --- | --- |
| `sex` | ATO source category, Male or Female |
| `taxable_status` | Taxable or Non Taxable, sampled from the ATO source cells |
| `age_range` | Label of the ATO age band |
| `taxable_income_bracket` | Label of the sampled ATO taxable-income bracket |
| `age_years` | Simulated age in years; the static sample uses ages 15-100 |
| `state` | State or territory category from ATO Table 6A |
| `postcode` | Geographic postcode category; may be missing for nonnumeric source categories |
| `industry` | Census G54 industry code; `ID_NS` is the fallback for unmatched groups |

Read `postcode` as text if its formatting matters. The source combines Census postal areas with ATO postcode categories; neither field is an individual's address.

## Fictional names

| Column | Meaning |
| --- | --- |
| `first_name` | Generated given name, using the source sex category when available |
| `last_name` | Generated surname |
| `full_name` | Given name and surname joined with a space, without titles |

These display names come from Faker's `en_AU` locale, not tax records or Census microdata. Their distribution is illustrative. They are unrelated to financial amounts or geography and may repeat. In the longitudinal panel, names are stable for each `agent_id`. The three columns are also included in the two backtest snapshots.

## Financial fields

| Column | Meaning |
| --- | --- |
| `taxable_income` | Simulated annual taxable income, using the sampled bracket and percentile refinement |
| `salary_or_wages` | Salary or wages |
| `allowances_tips_directors_fees` | Allowances, earnings, tips and directors' fees |
| `govt_allowances_payments` | Australian government allowances and payments |
| `govt_pensions_allowances` | Australian government pensions and allowances |
| `gross_interest` | Gross interest |
| `dividends_unfranked` | Unfranked dividends |
| `dividends_franked` | Franked dividends |
| `dividends_franking_credit` | Dividend franking credits |
| `deduction_car_expenses` | Work-related car expense deductions |
| `deduction_travel_expenses` | Work-related travel expense deductions |
| `deduction_uniform_expenses` | Work-related uniform and clothing expense deductions |
| `deduction_self_education` | Work-related self-education deductions |
| `deduction_other_work_related` | Other work-related expense deductions |
| `deduction_total_work_related` | Total work-related deductions, sampled separately from the categories |
| `deduction_gifts_donations` | Gift and donation deductions |
| `total_deductions` | Total deductions, sampled separately from component deductions |
| `net_rent_profit` | Rental profit item |
| `net_rent_loss` | Rental loss amount, recorded as a negative value |
| `total_income` | Total income item, sampled separately from taxable income |
| `reportable_employer_super` | Reportable employer superannuation contributions |
| `personal_super_contributions` | Personal superannuation contributions |
| `net_capital_gain` | Net capital gain |
| `help_debt_balance` | HELP debt balance, a balance rather than annual income |
| `net_tax` | Net tax item, sampled from published cell totals rather than calculated from income |
| `medicare_levy` | Medicare levy item, sampled rather than calculated |

The item sampler preserves the sign of each source cell's mean. Losses are negative, so net rental income is `net_rent_profit + net_rent_loss`. A zero cell mean or an absent item produces zero. A source cell containing a mix of positive and negative values supplies only its net mean; this model does not reconstruct that mix. Financial fields are not a reconciled tax return; adding components or subtracting deductions need not reproduce the independently drawn totals.

## Longitudinal and backtest outputs

The longitudinal panel adds `agent_id` and `year`. IDs are generated labels for simulated agents, including entrants. A row records one agent in one simulated year. The panel begins with a separate seeded draw, so its 2023 cohort differs from the static CSV.

Annual summaries contain `year`, `population`, `deaths`, `entrants`, `mean_age`, `mean_taxable_income`, `median_taxable_income` and `pct_taxable`. Backtest summaries also contain `sex_male_pct`. Percentage fields use 0-100 units.

Backtest snapshots have smaller financial item sets because the historical source tables differ. They omit geography and industry. Their column names use the same meanings as the main sample.
