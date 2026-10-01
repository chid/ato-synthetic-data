# Public company data

`data/companies/` contains real, named corporate tax disclosures published by the Australian Taxation Office. They are separate from the synthetic individual datasets. The latest release checked on 1 October 2026 is the [2024-25 Report of Entity Tax Information](https://data.gov.au/data/dataset/corporate-transparency). Its cut-off date is 1 August 2026.

## Files and scope

All 12 annual releases, 2013-14 through 2024-25, are downloaded and included as unchanged workbooks in `data/companies/workbooks/`. A separately catalogued 2019-20 workbook is also retained. Its binary checksum differs, but every tax-table row matches the main 2019-20 workbook. It is not counted twice.

The combined `income_tax_history.csv` contains 33,051 company-year records. `prrt_history.csv` contains 148 records and `mrrt_history.csv` contains 7. Each has `release_year`, `source_workbook`, `source_sheet` and `source_row` columns so a row can be traced back to its published cell values. Each `*_all_source_rows.csv` archive retains every table row across releases, including the first workbook's December, March and Combined income snapshots. The income-tax archive contains 34,910 rows and includes repeated snapshots. Use the history file for company-year counts and the archive for publication comparisons.

History selection uses the latest release for each ABN and income year. When ABN is missing, it uses the exact published name. It makes no fuzzy name matches, so a name change without an ABN can remain as separate observations. Within the first release, Combined takes precedence over the repeated December and March income snapshots. The entire selected row is retained, including blanks. A missing value is never filled from an older disclosure. Conflicting amounts for one entity-year at the same release and snapshot priority stop the build.

Historical financial values retain source decimals: the original 2014-15 and 2016-17 workbooks each contain a tax-payable amount with cents. Summary sums use decimal arithmetic. A historical workbook can combine multiple tax sections in one sheet. PRRT and MRRT headers determine the tax type, so their payments are never treated as total income. The current workbooks use separate tax sheets.

The latest release's files are:

- `companies_2024_25.csv`: 4,299 income-tax records for the 2024-25 income year.
- `late_returns_2024_25.csv`: 21 records for 2022-23 and 95 for 2023-24, published with the 2024-25 release.
- `prrt_2024_25.csv`: 21 petroleum resource rent tax records, kept separate from income tax.
- `summary_2024_25.csv`: three income-year summaries of record counts, published amount sums and blank counts.
- `source_2024_25.json`: attribution, source URLs, checksums and source controls for the exports.

The current income-tax disclosure threshold is total income of $100 million or more. Through 2021-22, Australian-owned resident private companies used a $200 million threshold, while Australian public and foreign-owned corporate tax entities used $100 million. From 2022-23, all these categories use $100 million. Counts across that change are not directly comparable. The data does not cover all Australian companies. The named tax entity may represent a consolidated tax group and does not necessarily correspond to an economic or accounting group. Do not treat a row as an individual operating subsidiary without further evidence.

PRRT uses its own disclosure scope. An entity may appear in both the income-tax and PRRT files. PRRT is a separate tax and is not included in the income-tax summary.

## Columns

| Column | Meaning |
| --- | --- |
| `company_name` | Entity name exactly as published in the workbook |
| `abn` | Published 11-digit Australian Business Number as text; blank when absent in the source |
| `total_income` | Published total income, annual AUD; income-tax files only |
| `taxable_income` | Published taxable income, annual AUD; income-tax files only |
| `tax_payable` | Published income tax payable, annual AUD; income-tax files only |
| `prrt_payable` | Published petroleum resource rent tax payable, annual AUD; PRRT file only |
| `income_year` | Source income-year label; on PRRT rows, taken from the workbook's release year |

The latest release uses integer dollars; historical amounts can include cents. No amount is estimated or recomputed. ATO's workbook explains that legislation does not permit reporting an amount of zero or less, so those fields are blank. A blank taxable-income field does not disclose a loss amount. A blank tax-payable field is not stored as a numeric zero. The main file has 961 blank taxable-income fields, 1,149 blank tax-payable fields and 31 blank ABNs.

Total income, taxable income and accounting profit are different concepts. This extract preserves cases where taxable income exceeds total income. A tax-payable-to-income ratio is not a statutory tax rate or a measure of tax avoidance. The workbook directs readers to [ATO's corporate tax-transparency guidance](https://www.ato.gov.au/businesses-and-organisations/corporate-tax-measures-and-assurance/large-business/corporate-tax-transparency).

## Current-year source totals

These sums include positive published amounts for the 4,299 current-year income-tax records. They exclude late returns and PRRT.

| Field | Published sum (AUD) |
| --- | ---: |
| `total_income` | 3,342,185,114,932 |
| `taxable_income` | 349,136,493,123 |
| `tax_payable` | 87,488,527,889 |

The PRRT file separately reports $1,872,820,121. The summary's `*_reported_sum` fields describe sums of disclosed amounts, rather than filling missing fields or asserting an undisclosed net total.

## Refresh and verify

```sh
# Download and verify every annual release, then build the combined history.
python3 scripts/build_company_history.py

# Verify all included original workbooks, annual CSVs and combined history offline.
python3 scripts/build_company_history.py --validate-only

# Rebuild from a previously downloaded catalogue snapshot and workbooks offline.
python3 scripts/build_company_history.py \
  --metadata data/raw/corporate-transparency.json --out-dir verification/history
```

`source_history.json` records each source resource, workbook checksum, section counts, output controls and history-selection rules. `history_summary.csv` reports company-year counts, disclosed amount sums and blank counts by tax type and income year. The annual exports remain separate from the combined history.

```sh
# Discover and download the latest named-company release.
python3 scripts/build_company_data.py

# Select a specific release.
python3 scripts/build_company_data.py --year 2024-25

# Validate the included CSV checksums, counts, amount sums, blanks and summary offline.
python3 scripts/build_company_data.py --validate-only --year 2024-25

# Also compare every record with a downloaded official workbook.
python3 scripts/build_company_data.py --validate-only --year 2024-25 \
  --workbook data/raw/2024-25-corporate-report-of-entity-tax-information.xlsx

# Rebuild offline in another directory.
python3 scripts/build_company_data.py --year 2024-25 \
  --workbook data/raw/2024-25-corporate-report-of-entity-tax-information.xlsx \
  --out-dir verification/companies
```

Refresh selects the largest income-year label among the official dataset's named workbook resources. It checks the source headers and stops if their schema changes. Output filenames include the release year, so a later annual release creates its own files. Rebuilding the same year overwrites that year's exports. The source workbook remains in the ignored `data/raw/` directory.

The CSVs use UTF-8. In pandas, retain string identifiers and nullable integer amounts:

```python
import pandas as pd

amounts = ["total_income", "taxable_income", "tax_payable"]
companies = pd.read_csv(
    "data/companies/companies_2024_25.csv",
    dtype={"company_name": "string", "abn": "string", **{c: "Int64" for c in amounts}},
    keep_default_na=False,
    na_values={c: [""] for c in ["abn", *amounts]},
)
```

## Reuse

Based on Australian Taxation Office data, Commonwealth of Australia. Source disclosures and these modified extracts retain [CC BY 3.0 Australia](https://creativecommons.org/licenses/by/3.0/au/). Credit the ATO and describe the modifications: CSV conversion, renamed columns, separate income years, PRRT release-year labels and summaries. The project's MIT licence applies to code and documentation. ATO does not endorse this project.
