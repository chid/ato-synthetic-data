# ATO synthetic and public tax data

Synthetic Australian individual tax records generated from published ATO, ABS and Census aggregate statistics. The main sample has 20,000 rows and 37 columns, calibrated to the 2022-23 income year.

The repository also includes [4,299 real named companies](data/companies/companies_2024_25.csv) from ATO's latest public corporate tax-transparency release, for 2024-25. These records retain the published names and financial figures and are stored separately from the synthetic people.

Every individual record is simulated from public aggregate tables. The individual model uses no real-person taxpayer records, names, tax file numbers, contact details or private account data. Its display names are fictional. Postcodes are geographic categories, and longitudinal `agent_id` values identify simulated people. This is an independent project, without government endorsement.

## Download the synthetic data

| File | Rows | Description |
| --- | ---: | --- |
| [synthetic_individuals.csv](synthetic/synthetic_individuals.csv) | 20,000 | Static 2022-23 sample |
| [longitudinal_panel.csv.gz](synthetic/longitudinal_panel.csv.gz) | 237,808 | Simulated histories for 2023-2033, compressed with gzip |
| [longitudinal_summary_by_year.csv](synthetic/longitudinal_summary_by_year.csv) | 11 | Annual population and income summaries |
| [backtest_2012_13_predicted_2022_23.csv](synthetic/backtest_2012_13_predicted_2022_23.csv) | 23,664 | Experimental ten-year projection |
| [backtest_2009_10_predicted_2022_23.csv](synthetic/backtest_2009_10_predicted_2022_23.csv) | 24,669 | Experimental thirteen-year projection |

The `synthetic/` directory also contains annual summaries for both backtests. Pandas reads the compressed panel directly:

```python
import pandas as pd

sample = pd.read_csv("synthetic/synthetic_individuals.csv", dtype={"postcode": "string"})
panel = pd.read_csv("synthetic/longitudinal_panel.csv.gz", dtype={"postcode": "string"})
```

Amounts are annual Australian dollars except `help_debt_balance`, which is a debt balance. See the [data dictionary](docs/data-dictionary.md) for the columns.

## Public company data

The [ATO 2024-25 corporate tax-transparency workbook](https://data.gov.au/data/dataset/corporate-transparency) was released on 1 October 2026. Its income-tax records cover corporate entities meeting ATO's disclosure threshold of $100 million total income. This is a large-company disclosure dataset, not a census of Australian companies.

| File | Rows | Description |
| --- | ---: | --- |
| [companies_2024_25.csv](data/companies/companies_2024_25.csv) | 4,299 | Real company names, published ABNs, total income, taxable income and tax payable |
| [late_returns_2024_25.csv](data/companies/late_returns_2024_25.csv) | 116 | Late 2022-23 and 2023-24 returns included in the same release |
| [prrt_2024_25.csv](data/companies/prrt_2024_25.csv) | 21 | Separately published petroleum resource rent tax records |
| [summary_2024_25.csv](data/companies/summary_2024_25.csv) | 3 | Income-tax counts, published dollar sums and blank counts by income year |

Amounts are annual AUD. ATO leaves amounts of zero or less blank, and the CSVs preserve those blanks. ABNs are text identifiers and remain blank where unpublished. The current-year published tax-payable amounts sum to $87,488,527,889. Late returns and PRRT are excluded from that sum.

Refresh from the latest release, or validate the included CSVs offline:

```sh
python3 scripts/build_company_data.py
python3 scripts/build_company_data.py --validate-only
```

The refresh downloads the official workbook into the ignored `data/raw/` directory, exports each source section and verifies every row against it. Use `--year 2024-25` to select that release explicitly. The [company data guide](docs/company-data.md) explains the fields, scope and offline reproduction. [Source metadata](data/companies/source_2024_25.json) records the source URL, licence, workbook checksum and export controls.

## Run the generator

Use Python 3.12 or newer. The supplied outputs were generated with Python 3.14 and the pinned dependencies.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 scripts/generate_synthetic.py --n 20000 --seed 42 --out synthetic/synthetic_individuals.csv
python3 scripts/validate_synthetic.py
```

All processed inputs needed for generation and validation are included. No credentials or source downloads are needed for these commands.

```sh
python3 scripts/simulate_longitudinal.py --n 20000 --years 10 --seed 42
python3 scripts/validate_longitudinal.py
python3 scripts/backtest_2012_13.py --n 20000 --years 10 --seed 42
python3 scripts/validate_backtest.py
python3 scripts/backtest_2009_10.py --n 20000 --years 13 --seed 42
python3 scripts/validate_backtest_2009_10.py
```

The simulation writes an uncompressed panel locally. The longitudinal validator reads that file when present, otherwise it reads the supplied gzip copy. Validation scripts print distribution comparisons; they do not enforce statistical pass/fail thresholds. Dataset checksums are in [SHA256SUMS](SHA256SUMS).

## How it works

The static generator samples sex, taxable status, age range and income bracket jointly from ATO Table 3A. It refines taxable income using Table 16B percentiles, draws ages using ABS population counts, assigns geography from ATO Table 6A, and assigns industry from Census G54. Financial items use published cell-level presence rates and means, with assumed Gamma distribution shapes. Item amounts preserve the source mean's sign, including negative rental losses.

The longitudinal model adds mortality, entrants and income rank persistence. Its income growth target is an assumption calibrated from historical aggregate growth. Backtests start from older tax tables and compare projected outcomes with the 2022-23 aggregates.

## Fictional names

Every population dataset includes `first_name`, `last_name` and `full_name`. Names use Faker's `en_AU` locale with an independent seeded random generator. The source sex category selects the given-name pool when available. Names are illustrative; their frequencies do not model Australian age or ancestry distributions, and they are unrelated to income or geography. Names may repeat, so use `agent_id` to identify a person in the longitudinal panel. Each agent keeps the same name across all their years, including new entrants.

Generate a separate CSV of names:

```sh
python3 scripts/generate_names.py --n 10 --seed 42
python3 scripts/generate_names.py --n 100 --seed 7 --out synthetic/names.csv
```

The first command prints CSV to stdout. Add `--sex Male` or `--sex Female` to select a given-name pool. Repeating a seed with the pinned Faker version gives the same names. Adding names does not change financial values or simulation results.

## Limitations

- Financial items are sampled separately. Their sum need not reconcile with taxable income, total deductions or net tax. These records are useful for experiments and demonstrations, rather than tax calculations.
- Item variance and some temporal relationships are assumptions. Matching aggregate distributions does not establish accurate individual correlations.
- Industry and postcode assignments combine sources with different populations and income concepts. Census postal areas also differ from postal delivery postcodes.
- Backtests hold historical taxable-status relationships fixed and can miss changes in tax policy. Historical observation periods do not prove that a source was available at the forecast date. See the [release-date correction](SOURCES.md#backtest-source-date-correction).

[APPROACH.md](APPROACH.md) and the [original workflow notes](docs/original-readme.md) preserve the development history and earlier results. Some passages describe earlier model versions. The commands and packaging above describe this public copy.

## Regression tests

```sh
python3 -m unittest discover -s tests -v
```

The tests check signed rental losses, seeded name generation, stable names for longitudinal agents, company release selection, preserved source blanks, CSV roundtrips and changed-file detection. The [verification notes](docs/verification.md) include current sample comparisons and company-source reconciliation.

## Sources and reuse

[SOURCES.md](SOURCES.md) lists the official publications, attribution and source licences. `data/processed/` contains reshaped public aggregates; `data/companies/` contains published corporate disclosures. Raw downloads, downloaded web archives and local environments are excluded. The older extraction scripts require separately downloaded files in `data/raw/`; the company refresh command downloads its own source.

The [MIT licence](LICENSE) covers the project's code and documentation. Source data retains its original licences. Project-created synthetic outputs are offered under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); retain the source attribution when redistributing them.
